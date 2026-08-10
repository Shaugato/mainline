<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# QUALITY & RELEASE — the repair plan

**Lead:** quality & release
**Date:** 2026-08-10
**Cluster used for every measurement below:** local Docker node `mainline-crdb`,
CockroachDB CCL **v26.2.5** (x86_64-pc-linux-gnu, built 2026/07/28, go1.25.5),
`postgresql://root@localhost:26257/…?sslmode=disable`.
**Interpreter used:** `.venv/Scripts/python.exe` — **Python 3.13.14**, not 3.14.

Everything in §1 was executed. Nothing in §1 is inferred.

---

## 1. MEASURED STATE — what is actually true this morning

### 1.1 The workspace does not exist as a workspace

| Fact | Measured |
|---|---|
| `uv` on this machine | **NOT INSTALLED.** `where uv`, `pipx`, `python -m uv` all fail. Every `just` recipe and 7 of 11 workflows begin with `uv`. |
| Distributions on disk | **27** `pyproject.toml` files (13 `packages/`, 14 `verticals/mainline/packages/`) |
| Distributions in `uv.lock` `[manifest] members` | **7** — `mainline-boundary`, `mainline-domain`, `mainline-recall-agent`, `trappoint-conformance`, `trappoint-jcs`, `trappoint-migrate`, `trappoint-recall` |
| Distributions installed in `.venv` before I started | **5** |
| Package directory with source but **no `pyproject.toml`** | `verticals/mainline/packages/mainline-corpus/` — 60+ modules under `src/mainline_corpus/`, imported by `tests/unit/moc_stream/`, `tests/security/injection/`, `tests/integration/schema/test_mi_event_severity.py` and `mainline_boundary.greps` |

**Consequence, and it is the single largest release blocker:** `uv lock --check` (ci.yml job 1)
and `uv sync --frozen --all-packages` (ci.yml job 2) **cannot pass today.** Every green tick
that CI has ever shown for those jobs was shown against a seven-member workspace that stopped
describing this repository twenty distributions ago.

### 1.2 The test suite — before and after installing the workspace

I installed all 26 installable distributions with `pip install -e --no-deps` and re-collected.

| | collected | collection errors |
|---|---|---|
| as found (5 packages installed) | 7 262 | **14** |
| after installing 26 | 8 339 | **3** |
| `verticals/**/tests` collected separately | 146 | 0 |

The 14 → 3 delta was entirely `ModuleNotFoundError` for uninstalled workspace members
(`mainline_mutation`, `mainline_domain`, `mainline_recall_agent`, `mainline_agentkit`,
`trappoint_model`). The residual **3 are module-basename collisions** under pytest's default
`prepend` import mode:

```
tests/integration/recall_schema/conftest.py  ->  imports tests/integration/recall_index/_support.py
packages/trappoint-sql/tests/test_cli.py     ->  shadowed by packages/mainline-boundary/tests/test_cli.py
tests/unit/domain/lattice/test_red_first.py  ->  shadowed by tests/e2e/mutation/test_red_first.py
```

A fourth is latent and fires the moment `verticals/**` joins `testpaths`:
`test_fingerprint_stability.py` exists in both `packages/trappoint-migrate/tests/` and
`verticals/mainline/packages/mainline-custody-patrol/tests/`.

I tested the two obvious levers and **both are wrong**, so no worker needs to spend a cycle on them:

* `--import-mode=importlib` — **worse**: 34 collection errors, because a dozen conftests do
  sibling imports (`from _support import …`, `from corpus… import …`) that depend on the
  rootdir `sys.path` insertion `prepend` performs.
* adding `__init__.py` to the colliding `tests/` directories — **fails**:
  `ImportPathMismatchError: ('tests.conftest', …mainline-boundary/tests/conftest.py, …trappoint-sql/tests/conftest.py)`.
  Both packages' test dirs become the module `tests`, so the collision merely moves.

**Renaming the four modules is the only fix that works. It is what W2 will do.**

### 1.3 `testpaths` excludes a fifth of the repository

Root `pyproject.toml` says `testpaths = ["tests", "packages"]`.
`verticals/*/packages/*/tests` — 146 collected tests across `mainline-anchor`,
`mainline-custody-patrol`, `mainline-sequencer` — **has never run in a default `pytest` invocation.**
Neither has `verticals/mainline/apps/console` (see §1.7).

### 1.4 The suite spawns thirteen CockroachDB clusters and kills the machine

This is the discovery that changes the shape of the wave. During the full-suite run I observed,
with `docker ps -a`:

```
mainline-cbm-test            cockroachdb/cockroach:latest-v26.2   Exited (7)
mainline-deltalattice-test   cockroachdb/cockroach:latest-v26.2   Exited (7)
mainline-directrix-test      cockroachdb/cockroach:latest-v26.2   Exited (7)
mainline-origindiff-test     cockroachdb/cockroach:latest-v26.2   Exited (7)
mainline-late-recall-test    cockroachdb/cockroach:latest-v26.2   Exited (8)
mainline-recall-index-test   cockroachdb/cockroach:latest-v26.2   Exited (7)
mainline-recall-lexical-test cockroachdb/cockroach:latest-v26.2   Exited (8)
mainline-blame-schema-test   cockroachdb/cockroach:latest-v26.2   Exited (7)
mainline-event-severity-…    cockroachdb/cockroach:latest-v26.2   Exited (8)
mainline-cbm-probe           cockroachdb/cockroach:latest-v26.2   Created
mainline-custody-nemesis     cockroachdb/cockroach:v26.2.5        Exited (7)
trappoint-model-differential cockroachdb/cockroach:v26.2.5        Exited (7)
trappoint-model-concurrency  cockroachdb/cockroach:v26.2.5        Exited (8)
```

Thirteen private single-node clusters, each `--cache=.25 --max-sql-memory=.25`, started
concurrently. Every one died with exit 7/8. **They took the real node `mainline-crdb` down with
them** (`server closed the connection unexpectedly`), and the Docker Desktop engine API started
answering `500 Internal Server Error`. Twenty-three source files spawn containers.

Two secondary facts fall out of the same table:

* **The image pin is not one constant.** `compose.yaml` claims it is
  ("THE VERSION CONSTANT LIVES HERE AND ONLY HERE"). Measured across `*.py`:
  **33 uses of `cockroachdb/cockroach:latest-v26.2` — a floating tag** — against 10 of the
  pinned `v26.2.5`. A floating tag is exactly the dev/CI skew the schema fingerprint exists
  to catch, introduced by the harness that is supposed to prevent it.
* **The suite hangs rather than fails when the cluster dies.** The full run sat at
  562 s CPU and stopped accumulating; `timeout = 120` in `pyproject.toml` did not fire.
  Fixtures connect without `connect_timeout`, so a dead node is an infinite wait, not a skip.

**There is no hermetic subset.** I then ran only `tests/unit tests/boundary tests/eval packages`
with `--timeout=60 --timeout-method=thread`, expecting a clean measurement. It hung too — 300 s of
CPU accumulating at roughly one CPU-second per wall minute, i.e. blocked, not computing — and
`docker ps` showed why: `packages/trappoint-model/tests` had started
`trappoint-model-differential` (`cockroachdb/cockroach:v26.2.5`) and was waiting on it.
`packages/` is in `testpaths` and `packages/` is not hermetic. **I could not obtain a full
pass/fail/error/skip census in this session**, and I am not going to invent one; producing that
census, per package, is W10's `done_when` and it becomes possible only once W2 has landed.
The explicit CLI `--timeout` did not fire either, because pytest-timeout's thread method does not
interrupt a hang that happens in *session-scoped fixture setup*.

Four environment-variable spellings are already honoured by those fixtures —
`MAINLINE_TEST_DSN` (28 occurrences), `COCKROACH_URL` (19), `CRDB_URL` (17),
`TRAPPOINT_DSN` (3) — and every fixture I read checks them **first**, before reaching for
Docker. That is the seam. One session-scoped cluster exported under all four names collapses
thirteen clusters into one **without editing a single domain conftest.**

### 1.5 Types are in good shape; lint is not

```
mypy --config-file mypy.ini  packages/trappoint-migrate/src  packages/trappoint-conformance/src
    -> Success: no issues found in 25 source files
mypy --config-file mypy.ini  jcs recall sql core diagnose verify mainline-boundary  (src)
    -> Found 1 error in 1 file (checked 129 source files)
       packages/mainline-boundary/src/mainline_boundary/iam.py:335  unused "type: ignore"
ruff check .           -> Found 896 errors
ruff format --check .  -> 237 files would be reformatted, 1040 already formatted
```

`mypy.ini` lists only five `mypy_path` entries and emits
`unused section(s): [mypy-trappoint_jcs.*], [mypy-trappoint_sql.*], [mypy-trappoint_core.*], …`
in one direction and the complementary set in the other — i.e. **no single invocation type-checks
the substrate**, which is why "129 files, 1 error" was news.

The 896 ruff findings are dominated by cosmetics (`D102` 162, `D401` 110, `PLR2004` 102,
`PT018` 64) but include ~96 in the classes `ruff.toml`'s own preamble calls load-bearing
(`E501` 61, `T201` 18, `S608` 15, `BLE001` 2).

### 1.6 Licensing: the `LICENSES/` directory is empty and the identifier is forked

`LICENSES/` contains nothing. Header census over `packages, verticals, spec, skills, scripts,
tests, infra, docs`, discounting files that already carry a `.license` sidecar:

| SPDX identifier in header | files |
|---|---|
| `FSL-1.1-ALv2` | 1 027 |
| `Apache-2.0` | 634 |
| `LicenseRef-FSL-1.1-ALv2` | 324 |
| `CC-BY-4.0` | 22 |
| **no header, no sidecar** | **4 738** (4 459 `.json`, 190 extensionless, 64 `.db`, 19 `.typed`, 18 `.txt`, 17 `.js`, 16 `.md`, …) |

Two defects: FSL-1.1-ALv2 is **not** an SPDX-registered identifier, so REUSE requires the
`LicenseRef-` form — and the repository uses **both spellings, 1 027 against 324**, for the same
licence. `verticals/mainline/apps/console/package.json` uses the `LicenseRef-` form.

### 1.7 CI: what exists, what is missing, what is vacuous

Eleven workflows exist. `ci.yml` and `db.yml` are real and detailed. Missing or broken:

* **`cloud-verify.yml` — does not exist.** Nothing ever runs against CockroachDB Cloud.
* **`supply-chain.yml` — does not exist.** `evidence/sbom/` does not exist either, though
  `boundary.yml` gates on the path.
* **No workflow touches the console.** `verticals/mainline/apps/console` has a complete
  `pnpm run ci` (eslint, tsc twice, vitest, vite build, budget check, licence check) and a
  committed `pnpm-lock.yaml`. **278 TypeScript files have zero CI.**
* `boundary.yml` gates on `verticals/mainline/packages/mainline-gate-svc/**` and `.importlinter`
  contract 1 forbids importing `mainline_gate_svc`. **The package does not exist.** Both are
  currently assertions about nothing.
* `claims.yml` gates on `docs/HONESTY.md`. **It does not exist.**
* `.importlinter` declares 5 `root_packages` out of 27 distributions. The `import-linter-registry`
  job in `ci.yml` is supposed to refuse a build when a distribution appears in neither
  `root_packages` nor a `forbidden_modules` list — **22 do.**

### 1.8 The central claim: one file stands between this repository and its proof

The merge-gate DDL **is now on disk** — `0050_permit.sql`, `0066_disposition.sql`,
`0071_merge_record.sql`, `0071c_refusal_ledger.sql`, `0115_fn_permit_merge_gate.sql`,
`0117_proc_merge_permit.sql`, `0130_trg_permit_merge_gate.sql`. The previous verifier's report
("the kernel gate does not exist in this tree", 2026-08-08, 105 files) is **out of date**; the
tree is 261 files and the gate is in it.

The Class-B failure is at **`0049z`**, and `(49,"z") < (50,"")`. A forward-only runner that stops
on first error therefore **never reaches 0050, let alone 0115.** One file is the whole distance
between the repository and its central claim.

I proved the exact semantics against the live node rather than reasoning about them:

```
CREATE TABLE fam_probe (id INT PRIMARY KEY, family STRING NOT NULL)    -> 42601
CREATE TABLE fam_probe (id INT PRIMARY KEY, "family" STRING NOT NULL)  -> OK
INSERT INTO fam_probe (id, family)  VALUES (1,'x')                     -> 42601
INSERT INTO fam_probe (id, "family") VALUES (2,'y')                    -> OK
SELECT id, family FROM fam_probe                                       -> 42601
SELECT id, "family" FROM fam_probe                                     -> OK
UPDATE fam_probe SET family = 'z' WHERE id = 1                         -> 42601
```

**Quoting the DDL is not sufficient.** `mainline_mutation/sql.py` emits the column name
unquoted in a column list (line 123) and reads it as an attribute (line 234); those statements
would fail at runtime with the same 42601. **The column must be renamed**, in the migration and
in its one Python consumer. A tree-wide scan for the same defect class over all 261 migrations
(`^\s+(family|index|constraint|role|view|table|column|order|limit|offset|primary|key|default|user|grant|window|range)\s+(STRING|INT|…)`)
returns **exactly one file**: `0049z`. This is not a class of bug in this tree; it is one bug.

### 1.9 Also observed, and worth a worker's ten seconds

* Ruff/mypy/pytest resolved in `.venv` are **ruff 0.16.1, mypy 2.3.0, pytest 9.1.1** against
  floors of `>=0.6`, `>=1.11`, `>=8.2` in the dev group. The floors are three major versions
  behind what is installed; `uv.lock` is the only thing making dev and CI agree, and §1.1 says
  the lock describes a seven-member workspace.
* A stray `trappoint.exe` from an earlier session held `.venv/Scripts/trappoint.exe` open and
  broke a `pip install`, leaving a corrupt `~rappoint-migrate` dist-info. Removed.
* The node reported `remote wall time is too far ahead (9.94 s) to be trustworthy` after a host
  sleep. `docker restart` clears it. Worth putting in the doctor script rather than in folklore.

---

## 2. STRATEGY — six decisions, one line each

**D1 — Fix the lockfile last, not first.** `uv.lock` is regenerated by W1, which `depends_on`
W2 and W6 because both create new distributions; a lock taken before them is stale on arrival.

**D2 — Rename the four colliding test modules; do not change import mode and do not add
`__init__.py`.** Both alternatives were measured (§1.2) and both are worse.

**D3 — Collapse thirteen clusters into one via a root `conftest.py` that exports all four DSN
spellings, not by editing thirteen domain conftests.** The fixtures already prefer an
environment DSN; the seam exists, so use it and touch nobody's files.

**D4 — Freeze lint and types with a counted ratchet, do not reformat 1 277 files mid-wave.**
`ruff format` would rewrite 237 files owned by nine other workers and every domain lead in the
building. A ratchet records today's honest number per rule per tree, CI refuses an increase, and
the number is published in `docs/HONESTY.md`. A truthful 896 that cannot grow beats a fabricated 0.

**D5 — Build `mainline-gate-svc` for real.** A contract that forbids importing a module that does
not exist proves nothing; the boundary claim ("no model can reach the merge gate") is only
falsifiable once there is a gate service whose dependency closure can be enumerated.

**D6 — One worker owns the product's central proof end to end, including the three files outside
this domain that block it.** W3 renames the `family` column, fixes its one Python consumer, and
then demonstrates the refusal. Deliberate cross-domain touch, enumerated, justified in §1.8,
recorded in `cross_domain_notes`. The five Class-A missing tables are **not** ours — they need
allocation-table numbers — so W3 records them as skips in the evidence rather than inventing them.

---

## 3. THE TEN WORKERS

| # | id | owns, in one line | depends on |
|---|---|---|---|
| 1 | `qr-workspace-lock` | root `pyproject.toml`, `uv.lock`, the missing `mainline-corpus` distribution | W2, W6 |
| 2 | `qr-suite-collects` | root `conftest.py`, `trappoint-testkit`, the four renames | — |
| 3 | `qr-gate-refusal-proof` | `0049z` rename, `scripts/proof/gate_refusal.py`, `release-proof.yml` | — |
| 4 | `qr-ruff-ratchet` | `ruff.toml`, `qa/ruff-ratchet.json`, the ratchet checker | — |
| 5 | `qr-mypy-strict` | `mypy.ini`, `scripts/qa/mypy_targets.py`, the one real error | — |
| 6 | `qr-boundary-contracts` | `.importlinter` (27 roots), `mainline-gate-svc` | — |
| 7 | `qr-reuse-licences` | `LICENSES/`, `REUSE.toml`, the compliance checker | — |
| 8 | `qr-workflows` | `ci`, `db`, `cloud-verify`, `supply-chain`, `console` | W1, W2, W4, W5, W6, W7 |
| 9 | `qr-one-command` | `justfile`, `compose.yaml`, `scripts/qa/doctor.py` | W2 |
| 10 | `qr-readme-honesty` | `README.md`, `docs/HONESTY.md`, the test-state reporter | W1–W9 |

Full briefs are carried in the dispatch structure. File ownership is literal and disjoint;
no worker may create, edit or delete a path it does not own.

---

## 4. WHAT "DONE" MEANS FOR THIS WAVE

A judge's first five minutes, in order, and the worker that owns each:

1. `git clone` → `README.md` states in its first screen what is proven and what is not, and links
   `docs/HONESTY.md` (W10).
2. `just doctor` says what is missing before anything fails obscurely (W9).
3. `just up && just prove` produces a **real refusal from the database**, written to
   `evidence/gate-refusal/` with the SQLSTATE, the constraint name and the chain report (W3).
4. `uv sync && pytest` runs on a fresh clone with no `PYTHONPATH` (W1, W2).
5. CI is green where it claims green and red where it is red, and `docs/HONESTY.md` says which is
   which, with numbers a skeptic can re-derive from `qa/*.json` (W4, W5, W7, W8, W10).

If W3 ends RED — if the gate refuses to refuse — that RED is published verbatim. PL-2 and the
project's moat both say a suite that has never been red asserts nothing.
