<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI repair — triage and plan

**Lead:** CI repair lead · **Date measured:** 2026-08-10 · **Source:** `gh run list`, `gh run view <id> --log-failed`
against runs `31371621773` (master, push) and the 2026-08-10T08:5x dependabot PR fan-out
(`31372088232` db, `31372088231` supply-chain, `31372088398` db-schema, `31372088425` custody-chain,
`31372088432` ci, `31372088500` console, `31372088311` boundary, `31372088271` release-proof,
`31372088227` submission, `31372057917` schema), plus local reproduction on
`postgresql://root@localhost:26257/defaultdb` with `.venv/Scripts/python.exe`.

Nothing in this plan deletes an assertion, adds `continue-on-error`, adds `|| true`, or touches
`docs/HONESTY.md`. Two of the fixes below *remove* an existing `|| true`.

---

## 0. The finding that outranks every entry in the brief's table

**Every workflow except `submission.yml` is triggered on `push: branches: [main]`. The repository's
default branch is `master`.**

Measured: `git branch --show-current` → `master`; `gh run list --branch main` → empty;
`gh run list --branch master --limit 25` → four Dependabot housekeeping runs, one `submission`
(push, failed), three scheduled `boundary` (failed). Every other workflow run in the last day is a
`pull_request` run on a Dependabot branch.

Consequence for the thing this repair exists to protect: when the repository goes public, the
Actions tab's default view is the default branch. A judge lands on a page whose only push-triggered
lane is `submission`, and it is red. Fifteen workflows have never run on `master` at all — so their
green would not be visible even after every fix below lands.

This is a class **(b)** CI-environment defect and it is worker **w1**'s first task. It costs one word
per file and it changes what a judge sees more than everything else combined.

---

## 1. Triage — three classes, every failing lane

Legend: **(a)** genuine product defect, fix the product · **(b)** CI-environment defect, fix the
workflow · **(c)** an assertion correctly reporting a true incompleteness — stays red, message made
precise.

| lane | measured failure | class | owner |
|---|---|---|---|
| all except `submission` | `push: branches: [main]`; default branch is `master` — the lane never runs on the branch a judge sees | **b** | w1 |
| **db** | `error: hostname of listen_addr must be "127.0.0.1" or "localhost"` → `the cluster never answered SQL`. `db.yml:325` passes `--listen-addr=0.0.0.0:26257`; CockroachDB v26.2.5 refuses to start. Same line in `mutation-ratchet.yml:199` and `nightly-differential.yml:89,206`. `db-schema.yml:162-173` already carries the *measured* working recipe — omit `--listen-addr` entirely | **b** | w2 |
| **ci → actionlint** | `custody-chain.yml:198` SC2015 (`… && { echo; exit 1; } \|\| true`) — also a banned `\|\| true`; `nightly-differential.yml:199` SC2034 unused `attempt` | **b** | w4, w2 |
| **boundary** (7/7 jobs) | `ModuleNotFoundError: No module named 'psycopg'` raised from `trappoint_testkit/cluster.py:60` while pytest loads the `trappoint_testkit.plugin` entry point. The lane installs `./packages/mainline-boundary pytest` and nothing else — deliberately, because E3 measures a minimal environment. The defect is that `trappoint_testkit/__init__.py` re-exports the whole cluster module, so importing the *image-pin and option-registration* helpers requires a live database driver | **a** (layering) + **b** | w3 |
| **release-proof** | `ERROR: Unknown config option: timeout` → exit 4. Root `pyproject.toml` sets `addopts = ["--strict-config", …]` and `timeout = 120`; the lane's `pip install "psycopg[binary,pool]" pytest` omits `pytest-timeout` | **b** | w3 |
| **db-schema** | `0139_trg_candidate_project.sql failed to apply — unknown function: mainline.fn_candidate_project()`, 4 errors in `tests/integration/recall_schema/`. **Root cause found; the local/CI divergence is the finding** — see §2 | **a** | w6 |
| **db-schema → mi-red** | `REFUSED: MI01/02/06/10/11/19/21/22/27/28 are pending but their tests pass — promote them in mi_catalogue.yaml` (10 invariants). The catalogue lags the tree | **a** | w7 |
| **db-schema → tier 0** | `packages/trappoint-migrate/tests/test_cli_offline.py::test_delegated_verb_actually_delegates_when_present` — the job runs `uv run --frozen --package trappoint-migrate`, an environment in which `trappoint-sql` is by construction absent, and the test asserts delegation *reaches* it. The test has an unstated precondition | **b** | w6 |
| **supply-chain** | `the resolved set did not contain ['mainline-domain','trappoint-core'], so the clean result below was measured over the wrong set`. **See §3 — the brief's reading of this log is wrong in an important way** | **a** (architecture) | w8 |
| **custody-chain → chain fn** | `A1 mainline.fn_cr_event_chain: 0106_fn_cr_event_chain.sql has DRIFTED from spec/custody/chain-verification.md §2` — 2 passed, 2 failed, 1 skipped. The checker states the direction is **forced**: the normative §2 body spells `NEW.field`, which on v26.2.5 creates but cannot weld (42P01, `no data source matches prefix: new`); the shipped body spells `(NEW).field`. The spec must move, not the migration. `check_chain_fn_matches_spec.py` is **present and tracked** — the brief's "absent" line was the `run:` block's own source text echoed into the log, not output | **a** (spec) | w4 |
| **custody-chain → K2** | `K2.2 NOT MET: spec/custody/checks.yaml still records check 14 with status 'deferred'`; also K2.1, K2.4, K2.5, K2.6 and `test_verifier_determinism`. Checks 13 and 14 declare `module: trappoint_verify.checks.structural`, `target_status: implemented`, and are unimplemented | **a** for 13/14 (offline, implementable) · **c** for whichever of K2.1/4/5/6 has no artefact | w5 |
| **console** | eslint: `no-useless-assignment` at `src/app/capability.ts:94` and `src/verify/ledger.ts:707`; `preserve-caught-error` at `src/data/contracts.ts:98` | **a** | w9 |
| **ci → mypy** | 9 errors in 7 files. `docx` import-not-found is a **config-location** defect: the `[[tool.mypy.overrides]] module = ["docx","docx.*"]` block lives in `verticals/mainline/packages/mainline-corpus/pyproject.toml:138`, which the root-config mypy invocation never reads | **a** | w9 |
| **submission** | path-length budget `EXCEEDED`: longest tracked path 218 > budget 214; 4 paths a 60-char clone prefix cannot check out > budget 2. Four console fixture frame files carry URL-escaped names up to 151 chars | **a** | w10 |
| **ci → REUSE** | `REFUSED [NO-LICENCE-TEXT] FSL-1.1-ALv2.` — a **trailing full stop** is being parsed into the identifier. Source: `verticals/mainline/apps/console/capture-plan.demo.json:2`, whose `$comment` reads `… SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2. The capture plan for …`. Also `non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254` — 41 new files use the bare spelling where the ratchet expects `LicenseRef-FSL-1.1-ALv2` | **a** | w10 |
| **schema** | `trappoint migrate: REFUSED: 0058_blocking_check: [42P01] relation "trappoint_ref.event" does not exist` in `packages/trappoint-sql/refvertical/sql`. A missing producer in the **reference** vertical, not in `mainline` | **a** | see §5 — deferred to wave 2 |
| **ci → ruff format** | `207 files would be reformatted` in CI; reproduced locally at `247 files would be reformatted, 1146 already formatted` with the same ruff 0.16.1 the lock pins. Not version drift — the tree is genuinely unformatted | **a** | see §5 — cannot be a worker, 247 files defeat literal enumeration |
| **ci → pytest --crdb=none** | `47 failed, 8182 passed, 833 skipped`. Mixed; see §4 | mixed | §4 |

---

## 2. `db-schema` — why the migration that applies locally fails in CI

It is **not** an environment difference. The two runs apply **different sets of migrations**.

Local: `trappoint migrate up` applies the whole `verticals/mainline/db/migrations` chain in numeric
order, 271/271. `0110_fn_candidate_project.sql` creates `mainline.fn_candidate_project()`;
`0139_trg_candidate_project.sql` welds a trigger to it 29 files later. In order, it works.

CI: `tests/integration/recall_schema/` applies a hand-declared subset. In
`tests/integration/recall_schema/_schema_support.py:50`:

```python
RECALL_MIGRATION_NUMBERS: tuple[int, ...] = (
    40,
    41,
    42,
    43,
    44,
    45,
    46,
    80,
    81,
    82,
    83,
    84,
    85,
    86,
    87,
    88,
    112,
    113,
    114,
    136,
    137,
    138,
    139,
)
```

**110 is not in the list.** The band claims — in that file's own docstring — that "the recall band
applies forward from clean on its own". That claim is false: `0139` depends on a producer at `0110`
that the band does not carry. The full-chain run can never expose it, because the full chain always
applies `0110` first. This is exactly the class of defect the brief asks to be treated as a finding
rather than a flake.

A second defect sits in the same selector, and is silent:

```python
head = path.name.split("_", 1)[0]
if head.isdigit():
```

`0138a_trg_cue_prefix_project_coarse.sql` has head `"0138a"`, `.isdigit()` is `False`, and the file
is dropped **without a word**. `0049b`, `0049c`, `0049d`, `0049y`, `0049z` exist elsewhere in the
tree, so this is a pattern, not a one-off. The `two files claim migration N` collision guard cannot
fire for suffixed files either.

**Fix (w6):** add `110` with a comment naming *why* (it is `0139`'s producer); make the head parser
accept an optional alphabetic suffix and order `0138 < 0138a < 0139`; and when a statement fails
with `UndefinedFunction`, name the producer file the band is missing rather than only the SQLSTATE.

---

## 3. `supply-chain` — what the log actually says, and the architecture underneath

The brief reports two strings. Only one of them was ever printed.

* `the resolved set did not contain ['mainline-domain','trappoint-core'], so the clean result below
  was vacuous` — **printed, in all six of the last six supply-chain runs.**
* `SECURITY CLAIM BROKEN: mainline-gate-svc now resolves …` — **never printed.** It appears in the
  logs only as part of the `run:` block's echoed *source*. Checked across runs `31372088231`,
  `31372058080`, `31371945797`, `31371788606`, `31371718663`, `31371705079`: the model-SDK
  intersection has been empty every time.

So the honest statement is: *the boundary is not observably broken; the instrument that would
observe it cannot see the graph it claims to measure, and its own anti-vacuity guard is what is
saying so.* That guard is correct and must stay.

Why it cannot see the graph. The step runs
`uv export --frozen --no-dev --package mainline-gate-svc --format requirements-txt`. `uv export`
emits **third-party distributions only**; workspace members either do not appear or appear as a
local/editable directive, and the parser at `supply-chain.yml:405` explicitly skips any line
starting with `-` or `--`. `REQUIRED = {"psycopg", "trappoint-core", "mainline-domain"}` therefore
cannot be satisfied by that command, ever. The measured resolved set is 12 names, all third-party:
`flexcache flexparser numpy pint platformdirs psycopg psycopg-binary psycopg-pool rapidfuzz scipy
typing-extensions tzdata`.

The architectural finding the numbers hand us for free: `mainline-gate-svc` declares three
dependencies and describes its own shortness as "the deliverable", but `mainline-domain` drags
**scipy, numpy, pint and rapidfuzz** into the closure of a service whose entire job is one
`SERIALIZABLE` transaction and one `CALL mainline.merge_permit`. Four BLAS/binary-wheel
distributions inside a determinism-critical merge gate is a boundary question in its own right,
independent of whether any of them is a model SDK.

**Fix (w8), and it is three things, not one:**

1. Re-found the assertion on a witness that *can* see workspace edges — `uv tree --frozen --package
   mainline-gate-svc` names `trappoint-core` and `mainline-domain` — and keep the export for the
   pins. Assert the model-SDK set is absent from **both**, and require **both** witnesses to name
   the workspace members. The anti-vacuity guard gets stronger, not weaker.
2. State the closure's real shape in the job summary — 12 distributions, listed — so a vacuous pass
   is impossible to mistake for a clean one at a glance.
3. Record the scipy/numpy/pint/rapidfuzz reach in `mainline-gate-svc/pyproject.toml`'s preamble and
   in `tests/test_no_model_in_closure.py` as a named, measured fact. If the gate does not need them,
   that is a `mainline-domain` split for wave 2; this wave must not pretend it isn't there.

---

## 4. `ci → pytest --crdb=none` — 47 failures, three classes in one lane

The lane is doing two incompatible jobs at once: it runs the ordinary suite *and* it runs suites
that are **red on purpose**. A judge cannot tell those apart, and neither can a contributor.

Red by design (class **c**), and named as such by their own assertion text:

* `tests/eval/recall/test_g4alpha_gates.py` — 5 failures, all `[FAIL] <metric> (floor: …)`. The
  `g4alpha` marker is registered in `pyproject.toml` as "observed RED by design until K4".
* `tests/integration/schema/test_mi_ratchet.py::test_red_every_invariant_is_enforced` —
  `28 of 30 MAINLINE invariants …`.
* `tests/integration/schema/test_mi_blame.py` (3), `test_mi_boundary_override.py` (4),
  `test_mi_event_severity.py` (1) — every message begins `PL-2 RED` or `MI26 RED`.
* `tests/integration/custody/test_k2_exit.py::test_verifier_determinism` — `Failed: wire the
  determinism assertion when trappoint-verify …`.

Genuinely broken (class **a**), and owned above or in wave 2:

* `packages/mainline-agentkit/tests/test_transport_residency.py::test_the_offline_path_imports_no_aws_sdk`
  — `boto3 was imported during an offline test run: the lazy import … has been moved`. **This is a
  real determinism-boundary regression** and belongs with w8's finding, not with lint.
* `packages/mainline-boundary/tests/test_cli.py` + `tests/boundary/test_ci_greps.py` — two
  un-exempted `temperature` sampling parameters in
  `packages/trappoint-recall/src/trappoint_recall/lexical/units.py:67` and
  `verticals/mainline/packages/mainline-domain/src/mainline_domain/quantity/units.py:262`.
* `packages/trappoint-conformance/tests/test_anomaly_coverage.py` and
  `tests/integration/custody/nemesis/test_ledger_attacks.py` — `ImportError: cannot import name
  '_case_id_of' from 'conftest'`; a cross-suite conftest reach.
* `tests/integration/algorithms/registry/test_0207_shape.py` — 8 failures, `migration … `.
* `tests/release/test_ruff_ratchet.py`, `test_mypy_covers_workspace.py`, `test_check_reuse.py`,
  `test_honesty_is_checkable.py` — these are the ratchets **correctly** reporting §1's ruff, mypy and
  REUSE failures. They go green when their causes do; they must not be touched directly.

**Structural fix (w1, inside `ci.yml`):** deselect the by-design-RED markers from the general lane
and give them a dedicated job that asserts *they are red* — the inverted-assertion pattern this
repository already uses in `db-schema.yml`'s `mi-red` job. Nothing is skipped, nothing is
`xfail`-swallowed: a by-design red that goes green fails the new job loudly, which is the property
that makes the pattern honest.

---

## 5. What this wave deliberately does **not** own

* **`ruff format` — 247 files.** Reproduced locally with the pinned ruff 0.16.1, so it is a real
  product state and not drift. It cannot be a worker here because the file-ownership rule requires
  literally enumerated paths and 247 of them is not a brief, it is a diff. It is a single mechanical
  commit (`ruff format .`) that must land **alone**, before or after this wave, never inside it —
  otherwise it hides every other diff in this plan. `tests/release/test_ruff_ratchet.py` stays red
  until it lands, and that red is telling the truth.
* **`schema` / the reference vertical.** `0058_blocking_check` refuses with `relation
  "trappoint_ref.event" does not exist` in `packages/trappoint-sql/refvertical/sql`. Same *shape* as
  §2 (a missing producer) but a different tree with a different owner; folding it in would put two
  unrelated SQL trees under one worker.
* **`docs/HONESTY.md`** is not edited by anybody in this wave.

---

## 6. Genuinely red after this wave, and why that is correct

| assertion | truth it reports |
|---|---|
| `tests/eval/recall/test_g4alpha_gates.py` (5) | the G4-alpha recall gates are not met; RED until K4 by declaration |
| `tests/integration/schema/test_mi_ratchet.py::test_red_every_invariant_is_enforced` | 28 of 30 MI invariants are not yet enforced |
| `tests/integration/schema/test_mi_blame.py` PL-2/MI26 reds (3) | the monotone guard and closure projection do not exist yet |
| `tests/integration/schema/test_mi_boundary_override.py` PL-2 reds (4) | `fn_boundary_project`, the carried-use projection and two append-only triggers do not exist yet |
| `tests/integration/schema/test_mi_spine.py::test_mi15_…` | MI15's BEFORE INSERT monotone guard does not exist |
| `tests/integration/custody/test_k2_exit.py::test_verifier_determinism` | the determinism assertion is unwired |
| `tests/release/test_ruff_ratchet.py` | 247 files are unformatted (§5) |
| `.github/workflows/schema.yml` | the reference vertical's `0058` has no producer (§5) |
| K2.1 / K2.4 / K2.5 / K2.6 — whichever w5 measures as having no artefact | the criterion has not been met |

Each of these gets a *message* improvement from its owner — name the missing object, name the owner,
name the file that would make it green — and keeps its exit code.

---

## 7. Workers

Ten workers, strictly disjoint literally-enumerated paths. Anything a worker notices outside its own
list goes to `cross_domain_notes`; it does not touch it.

| id | title | files |
|---|---|---|
| w1 | Actions visible on `master`, and the RED-by-design lane split | 9 workflow files |
| w2 | The CockroachDB container that never starts | `db.yml`, `mutation-ratchet.yml`, `nightly-differential.yml` |
| w3 | The boundary lane's import floor | testkit ×3, root `conftest.py`, `boundary.yml`, `release-proof.yml` |
| w4 | Custody: SC2015, the banned `\|\| true`, and the forced spec direction | `custody-chain.yml`, `spec/custody/chain-verification.md` |
| w5 | Custody check 14 exists, or K2.2 says precisely why not | `checks.yaml`, `structural.py`, its test, the attack matrix, `test_k2_exit.py` |
| w6 | The recall band's missing producer | `_schema_support.py`, `db-schema.yml` |
| w7 | The MI catalogue catches up with the tree | `mi_catalogue.yaml`, `mi_ratchet.py` |
| w8 | The gate service's determinism boundary | `supply-chain.yml`, gate-svc `pyproject.toml`, closure test |
| w9 | Both type-checkers | 3 TS files, 6 Python files, 2 `pyproject.toml` |
| w10 | A stranger can clone it, and every file names its licence | 4 frame files, 2 manifests, capture plan, capture script, budget, checker |

Full briefs are carried in the structured output that accompanies this document.
