<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Measured 2026-08-10 by the final proof agent, against the live local node, from the
working tree at `D:/CoackroachDBxAWS/mainline`.** Nothing here is quoted from a worker's
self-report. Every claim carries the command that produced it and the output that came
back. Where a claim could not be established, this document says so and names what is
missing.

Read the two headline findings first. They point in opposite directions and both are true.

> **1. THE GATE REFUSES. It is real, and it survives adversarial inspection.**
> The database refused a permit merge whose recalled precursor carried no signed
> disposition — `23514 gate_closed_when_issued` on the ordinary path, and
> `P0001 mainline.fn_permit_merge_gate` when the projected counter was forged to zero.
> The second refusal is the load-bearing one: the gate function re-derived the open
> obligation count from the base tables and refused a write whose counter said the
> obligation was closed. That refusal owes nothing to any counter, any client, or any
> projection. It is the product's central claim, and it is now demonstrated.
>
> **2. THE REPOSITORY A JUDGE WOULD CLONE DOES NOT CONTAIN THE PROOF.**
> `scripts/proof/`, `scripts/qa/`, `qa/`, `LICENSES/`, `conftest.py`,
> `packages/trappoint-testkit/` and `verticals/mainline/packages/mainline-gate-svc/` are
> **untracked**. `git clone` of `github.com/Shaugato/mainline` produces a tree in which
> `just doctor`, `just prove` and `pytest` cannot run and CI cannot start. This is a
> `git add` away from being fixed and is, in the judge's five minutes, fatal.

---

## 0 · The machine these numbers came from

| | |
|---|---|
| Cluster | `CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28)`, container `mainline-crdb`, `postgresql://root@127.0.0.1:26257/…?sslmode=disable` |
| Zone | every throwaway database created with `gc.ttlseconds = 4500` (Cloud Basic's value, the stricter of the two) |
| Interpreter | `.venv/Scripts/python.exe` — Python 3.13.14, 30 workspace distributions installed editable |
| Tree | working tree, **58 uncommitted paths** (see §4.1); HEAD is `174b29f` |
| Source census | 1,145 `.py` · 390 `.sql` · 278 `.ts`/`.tsx` · 261 migrations |

`uv` and `just` are **not on `PATH`** on this machine; `uv.exe` exists only inside
`.venv/Scripts/`. Every command below was therefore run with the venv interpreter
directly. That substitution changes nothing about what the database did.

---

## 1 · PROVEN

### 1.1 The migration chain applies 246 of 261 files, and the 15 that fail have one cause

```
$ ./.venv/Scripts/trappoint.exe migrate bootstrap --dsn '…/proof_chain'
bootstrapped: schema, schema_migration, schema_lock, schema_attestation, genesis attestation

$ ./.venv/Scripts/trappoint.exe migrate up --dsn '…/proof_chain' \
      --tree mainline --migrations verticals/mainline/db/migrations
trappoint migrate: REFUSED: 0121_trg_check_materialised: [42P01] relation "mainline_ops.outbox" does not exist
                                                                                   (7m04s)
$ … SELECT state, count(*) FROM trappoint.schema_migration WHERE tree='mainline' GROUP BY state;
applied  155
dirty      1
```

The real runner is forward-only and halts on the first refusal, which is correct for a
deployment and useless for a census. Applying the same files with the runner's own
`discover()` and `execute_ddl()`, continuing past failures, into a separately
bootstrapped database:

```
246/261 applied in 55.3s; 15 failed
```

**All 15 failures are `42P01`, and every one names one of five tables that no migration
creates.** `grep -rlE "CREATE TABLE[^;]*<name>"` over `verticals/mainline/db/migrations`
and `packages/trappoint-sql` returns **zero producer files** for each:

| missing table | migrations it breaks |
|---|---|
| `mainline_ops.outbox` | `0121_trg_check_materialised`, `0198x_no_rls_on_cdc_sources` |
| `mainline.identity_assignment` | `0145a_trg_cbm_account_guard` |
| `mainline.patrol_run` | `0163_v_fixity_coverage` |
| `mainline_meas.agent_action` | `0164_v_agent_actions`, `0165_v_gate_latency_daily`, `0166_v_txn_restart_daily` |
| `mainline_meas.standing` | `0171_v_standing_components`, `0172_v_my_record`, `0187_standing_rls_enable`, `0187a`, `0187b`, `0187c`, `0187d`, `0187e` |

**The two other failure classes reported by the previous wave are CLOSED.**

* **Class B (syntax) is fixed.** `0049z_meas_mutation_result.sql` applied. The column was
  renamed `mutation_family`; the file's own header records that `"family"` would have
  been legal in DDL but not everywhere it is read, so quoting was rejected in favour of
  renaming. `mainline_meas.mutation_result` exists in the applied schema.
* **Class C was never a bug.** `0119a_fn_explain_refusal.sql` applies once
  `trappoint migrate bootstrap` has run, exactly as ruling D6 says. Confirmed by its
  absence from the failure list above.

### 1.2 The attestation chain is gap-free and reports no drift

```
$ ./.venv/Scripts/trappoint.exe migrate attest --dsn '…/proof_chain'
fingerprint d648982556bd633cacaebb302cd78072037e336569cf1b517331a83d67c17e7b
grade       strong (covers: schemas, types, tables, triggers, routines)
chain head  ordinal 155 · d648982556bd633cacaebb302cd78072037e336569cf1b517331a83d67c17e7b
no drift
```

156 attestation rows, head at ordinal 155, one per applied migration plus genesis. The
CAS sequencing works; no sequence, no `unique_rowid()`.

### 1.3 THE GATE REFUSES — the central claim, measured

```
$ ./.venv/Scripts/python.exe scripts/proof/gate_refusal.py \
      --dsn 'postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable' \
      --database proof_gate_final --keep
cluster       CockroachDB CCL v26.2.5 …
chain         246/261 applied, 15 failed, 35.033s
reached 0115  True
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
VERDICT       PROVEN
```

**I did not take that at face value.** I re-ran the same history through my own harness,
in eight independently created and independently migrated databases, one per probe, and
read the mechanism inventory out of `pg_trigger` / `pg_constraint` before each attempt.

| probe | trigger present | CHECK present | projected `open_blocking` | derived open obligations | outcome |
|---|---|---|---|---|---|
| A0 baseline | yes | yes | 1 | 1 | **REFUSED `23514 gate_closed_when_issued`** |
| A1 − trigger | **no** | yes | 1 | 1 | **REFUSED `23514 gate_closed_when_issued`** |
| A2 − CHECK | yes | **no** | 1 | 1 | ADMITTED `00000` |
| A3 − both | **no** | **no** | 1 | 1 | ADMITTED `00000` |
| B0 drift baseline | yes | yes | **0 (forged)** | 1 | **REFUSED `P0001 mainline.fn_permit_merge_gate`** |
| B1 drift − trigger | **no** | yes | 0 | 1 | ADMITTED `00000` |
| B2 drift − CHECK | yes | **no** | 0 | 1 | **REFUSED `P0001 mainline.fn_permit_merge_gate`** |
| B3 drift − both | **no** | **no** | 0 | 1 | ADMITTED `00000` |

The exact refusals, verbatim from the database:

```
23514  failed to satisfy CHECK constraint
       ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))

P0001  MAINLINE: merge refused by mainline.fn_permit_merge_gate
       — re-derived open obligation count is 1 while the projected counter reads zero
```

**What is proven by this.** The refusal is the database's, not the client's. The `P0001`
arm is the one that matters: the counter said zero, the base tables said one, and the
gate believed the base tables. Rule P-2 — *a projection is enforced, never trusted* — is
not a slogan here; it is observable, and it is observable precisely because the write
that the CHECK would have waved through was refused anyway.

### 1.4 MEASURED REFUSAL DEPTH = 1, on both paths

Read the table again with only the removals in view. On the ordinary path exactly one
mechanism refuses (`gate_closed_when_issued`) and removing it admits the write. On the
drift path exactly one mechanism refuses (`fn_permit_merge_gate`) and removing it admits
the write. **Neither is a second weld for the other.**

This is not a discovered defect; it is a documented decision whose consequence had not
been measured on the MAINLINE tree until now. `0115_fn_permit_merge_gate.sql` says so in
its own header: the function *deliberately declines to decide* when the projection agrees
with the re-derivation, because raising an unnamed `P0001` over a named `23514` would
trade the exhibit for nothing. `packages/trappoint-conformance/REFUSAL_DEPTH.md` reports
the same depth of 1 for the reference vertical and records the pre-committed response —
*cut the mechanism, do not ship it.* **My measurement extends that finding from the
reference vertical to the shipped MAINLINE schema.** The architecture's sentence *"delete
the RAISE and the write still fails twice over"* is **NOT TRUE** of this schema, and the
number is now in front of the decision.

### 1.5 What the shipped schema actually does on the natural path — and the one table between it and a complete loop

`0121_trg_check_materialised` cannot apply, so the trigger that *increments*
`open_blocking` is absent from the applied schema. The trigger that *decrements* it
(`disposition.disposition_close`, from `0122`) is present. The counter therefore has a
consumer and no producer. `just prove` writes the counter itself and discloses that in a
caveat. I measured what happens when nobody writes it — i.e. what a real deployment of
this schema would do:

```
natural open_blocking = 0 (column DEFAULT; no trigger maintains it)
C1  merge, obligation open        -> REFUSED [P0001] mainline.fn_permit_merge_gate
C2  sign a disposition            -> REFUSED [23514] ctr_nonneg
C3  merge after the attempt       -> REFUSED [P0001] mainline.fn_permit_merge_gate
```

**On the shipped schema the gate can never be opened.** The disposition that would close
the obligation drives the counter to −1 and `ctr_nonneg` refuses it, so the merge refuses
forever. By the repository's own standard — *a gate that always refuses is a broken gate,
not a safe one* — the admission half of the claim is **not reachable on the tree as it
stands**. The `ADMISSION ADMITTED` line in `just prove` is reachable only because the
proof script stands in for the missing trigger.

I then measured how far away the complete loop is. Counterfactual, in memory only,
nothing written to the repository: supply a minimal `mainline_ops.outbox`
(`outbox_id, kind, subject_id, site_id, max_severity, payload, emitted_at` — the column
set is fixed verbatim by the only `INSERT` in the tree, `0101_fn_check_materialised.sql`
line 91) before the chain runs.

```
chain 248/261  failed=13          (0121 and 0198x now apply)
projection trigger check_materialised present: True
counter_source: trigger check_materialised -> mainline.fn_check_materialised
open_blocking maintained by the DATABASE = 1     ← no script wrote this
D1  merge, obligation open        -> REFUSED [23514] gate_closed_when_issued
D2  sign a disposition            -> signed; open_blocking -> 0
D3  merge after signed disposition-> ADMITTED [00000]
```

**Refuse → dispose → admit, end to end, with the counter maintained by the database and
no caveat.** One table, seven columns, is the entire distance between the proof this
repository can currently make and the proof it claims. That table needs a number from a
band whose owner and mode match in
`verticals/mainline/db/migrations.allocation.toml`; I own no band and did not create it.

### 1.6 Static gates that are green

| gate | command | result |
|---|---|---|
| import-linter | `lint-imports --config .importlinter` | **7 kept, 0 broken** · 537 files, 3,466 dependencies |
| mypy (strict substrate) | `mypy --config-file mypy.ini packages/trappoint-migrate/src/… packages/trappoint-conformance/src/…` | **Success: no issues found in 25 source files** |
| SQL migration lint | `trappoint migrate lint --root …refvertical/sql --root …db/migrations --root …templates` | **401 files, no findings** — no sequence, every migration cites an invariant, every header answers MI/I/COUNSEL-GATED/RATIONALE |
| workspace membership | `python scripts/qa/check_workspace_members.py` | tree and `uv.lock` agree: 30 distributions, 30 locked members |
| import registry | `python scripts/qa/check_import_registry.py` | 30 distributions, 29 root packages, 7 contracts, none unlinted |
| ruff ratchet | `python scripts/qa/ruff_ratchet.py` | **OK — no rule/tree count increased**; 28 entries can be tightened |
| console typecheck | `pnpm run typecheck` | clean (`tsc` twice, `--noEmit`) |
| console eslint | `pnpm run lint` | clean (`--max-warnings 0`) |
| console vitest | `pnpm run test` | **78 files, 1,438 tests, 1,438 passed** |

### 1.7 The Python suite is overwhelmingly green

```
$ ./.venv/Scripts/python.exe -m pytest --crdb=none -q
44 failed, 8066 passed, 739 skipped, 2 warnings in 435.54s
```

Collected per root: `tests/` 7,037 · `packages/` 1,605 · `verticals/*/packages/*/tests`
207 = 8,849. The 739 skips are cluster tests declining to start a private container under
`--crdb=none`, each with the named reason its own fixture writes. §3.4 classifies all 44
failures.

---

## 2 · BUILT BUT UNPROVEN

### 2.1 The conformance corpus has never run against MAINLINE

74 case modules exist. The manifest declares 71 cases for the `mainline` profile. Here is
what happens when they are actually run.

**As shipped.** `trappoint-conform` sees **one** implementation:

```
$ ./.venv/Scripts/trappoint-conform.exe --profile mainline --list
implemented 1 / 71
$ ./.venv/Scripts/trappoint-conform.exe --dsn '…/conf_mainline' --profile mainline
FAIL  CF-01 …
0/71 · spec 1.0.0-rc.1 · profile mainline · failed 1 · skipped 25 · pending 45   (exit 1)
```

Two structural reasons, both mechanical:

1. **The CLI never loads the corpus.** `cases/` is not in the wheel
   (`[tool.hatch.build.targets.wheel] packages = ["src/trappoint_conformance"]`) and
   nothing in `cli.py` calls `cases.load_all()`. Only CF-01, registered inline by
   `runner.py`, is in the registry. The package's *own* tests call `cases.load_all()`;
   the shipped entry point does not.
2. **No capability token is ever satisfied.** `_requirements_met` compares against
   `--requires` flags only — nothing probes the catalogue. `mainline.person` and
   `mainline.boundary_certificate` exist in the applied schema and their cases skip
   anyway.

**Run properly** — `cases.load_all()` called, and every `requires` token checked against
`information_schema` / `pg_roles` / `pg_policies` on the live database, each case isolated
on its own connection:

```
71 cases · 70 modules discovered · 71 implementations registered
capability tokens: 23 declared, 15 satisfiable, 8 not

passed                 2   CF-48, CF-69
failed                 1   CF-01
cannot-run: setup     59
cannot-run: capability 9
```

**All 59 setup failures share one cause.** `cases/_world.py::site_row` runs

```sql
INSERT INTO {s}.site (site_id, site_code, site_role) VALUES (%s, %s, %s)
```

against `mainline.site`, which declares `tenant_id UUID NOT NULL` and
`taxonomy_ver INT4 NOT NULL` with no defaults, and a `site_code_is_lower_case` CHECK that
the builder's `f"CONF-{…}"` violates. The corpus's world builder was written against the
reference vertical's `site` and has never been executed against MAINLINE.

I measured how much is behind that one door — patched in memory, nothing written:

```
passed 10   (CF-13 CF-14 CF-15 CF-16 CF-17 CF-39 CF-46 CF-48 CF-55 CF-69)
failed  5   (CF-01, CF-42, CF-60, CF-63, CF-67)
cannot-run: setup 47   — next wall is `clause_version`, same class of shape mismatch
cannot-run: capability 9
```

**Status: the corpus is written, and it has never told anyone anything about MAINLINE.**
It is a bounded repair — a world builder that matches the shipped schema — not a design
fault. Note also that `runner.run` catches `psycopg.Error` but not
`cases._world.SetupRefused`, so one broken builder aborts the entire run and no census is
possible; I had to write my own loop to get the numbers above.

### 2.2 CF-01, the one case the shipped CLI runs, fails

```
FAIL CF-01  expected 23514 on 'gate_closed_when_issued'; observed 23502 …
            Message: null value in column "site_role" violates not-null constraint
```

The case's own setup, not the gate. Note the irony worth stating plainly: **CF-01 is the
red-before-green artefact PL-2 rests on, and it is currently red for a reason that has
nothing to do with the gate.** The gate itself refuses that exact history correctly — §1.3
probe A0 is CF-01's history and it produced `23514 gate_closed_when_issued`.

### 2.3 Cluster-dependent tests: 739 skipped, and a skip is not evidence

Every skipped test names its own reason and most say so bluntly — *"A SKIPPED RUN IS NOT
EVIDENCE: the gate is a database mechanism and nothing in this package can stand in for
it."* `just test-cluster` (`pytest --crdb=reuse`) was **not** run here: the repository's
own justfile records that an unqualified full-suite run started thirteen private
single-node containers, all of which exited 7 or 8 and took the real node down. That is
the correct guard, and it means the cluster lane's true result is **unmeasured** in this
report.

### 2.4 `evidence/` claims with no generator run in this wave

`evidence/CUSTODY_ATTACK_MATRIX.md`, `evidence/custody-nemesis-run.json`,
`evidence/ccloud/`, `evidence/mutation/`, `evidence/reference-ledger/` were read but not
regenerated. `tests/integration/custody/test_k2_exit.py` fails against them (§3.4 class
E), which is itself evidence that the K2 exit criteria are not met.

---

## 3 · BROKEN

### 3.1 `ruff check` is red: 786 findings, 237 files unformatted

```
$ ./.venv/Scripts/ruff.exe check .
Found 786 errors.   [147 fixable]
$ ./.venv/Scripts/ruff.exe format --check .
237 files would be reformatted, 1082 files already formatted
```

Top rules: `D102` 162, `D401` 110, `E501` 61, `I001` 61, `PLR2004` 55, `RUF100` 54.

The project's policy is a ratchet, not zero, and **the ratchet passes** (baseline 847,
measured 786 — a fall of 61). But `just lint-py` runs bare `ruff check .` and
`ruff format --check .`, both of which exit non-zero. **`just lint` fails today.** The
recipe and the policy disagree, and the recipe is what a contributor types.

### 3.2 Workspace-wide mypy: 5 errors in 5 files

```
$ mypy --config-file mypy.ini $(python scripts/qa/mypy_targets.py)
Found 5 errors in 5 files (checked 572 source files)
```

Named example: `mainline-recall-agent/src/mainline_recall_agent/run/probabilistic.py:431`
— `Incompatible types in assignment (expression has type "Mapping[str, Any]", variable
has type "dict[str, Any]")`; and `run/orchestrator.py:886` — `Unused "type: ignore"`.
`tests/release/test_mypy_covers_workspace.py::test_check_passes_on_the_real_tree` catches
this, and it is one of the 44 failures.

### 3.3 The migrations lockfile is stale, for exactly the file that was repaired

```
$ ./.venv/Scripts/trappoint.exe migrate lock
! 0049z_meas_mutation_result.sql: manifest says sha256='1d993f87…', the tree says 'b18fee0d…'
! regenerate with `trappoint migrate lock --write`; the manifest is derived, never authored (MR-6 lock 1)
```

The `FAMILY` repair landed and `migrations.lock.json` was not regenerated. One command.

### 3.4 The 44 test failures, by cause

| # | class | failures | what it means |
|---|---|---|---|
| A | **`0207` migration was never written** | 8 in `test_0207_shape.py` + 1 in `test_novelty_manifest[directrix]` | `RuntimeError: migration 0207 is missing from …/db/migrations`. `directrix.yaml` claims `0207_v_safe_direction_current.sql` implements it. The test's own words: *a fragment whose evidence points at a file nobody wrote is the most expensive kind of wrong, because it reads as proof.* |
| B | **deliberate PL-2 red** | 8 | Each asserts *"PL-2 RED, as intended"* — `fn_boundary_project`, the carried-use projection, append-only on `carried_disposition_use`/`predicate_revocation`, the stale-lease hole, `sev_max` projection, severity-revision provenance, the MI-26 monotone guard. Honest, expected, and still red in CI. |
| C | **MI ratchet** | 1 | `28 of 30 MAINLINE invariants are still pending: MI01…MI30` (all but two). The invariant catalogue is almost entirely unpromoted. |
| D | **G4-alpha recall quality floors** | 5 | `retro_recall@3 sev5`, `p@block`, `nuisance_rate`, `mean_blocking_checks_per_permit`, `silence_conservation_l3` all below their declared floors. Real quality gates, genuinely failing. |
| E | **K2 custody exit criteria** | 6 | `evidence/k2-checkpoint-cadence.json` and `evidence/k2-migration-attestation.json` **do not exist**; the attack matrix does not record A1 as detected by check 3 or A10 by check 14; `spec/CHANGELOG.md` carries no `wire/checkpoint.md` v1.0 entry; the determinism assertion is an unwired `Failed:` stub. |
| F | **cross-package `conftest` collision** | 2 | `ImportError: cannot import name 'FIXTURE_DDL' from 'conftest' (…/packages/trappoint-model/tests/conftest.py)`. Several `tests/` directories lack `__init__.py`, so `import conftest` resolves to whichever one is first on `sys.path`. Infrastructure bug, not a product bug. |
| G | **grep/scanner violations** | 3 | boundary grep 2 violations over 757 and 3,080 files; injection scanner: `mainline-corpus/src/mainline_corpus/render/bedrock.py:126` — *dict literal key `'tools'` constructs a tool surface; the quarantined call shape holds no tools*. |
| H | **derived artefacts stale / declarations out of sync** | 5 | `migrations.lock.json` (§3.3); mypy ratchet missing `mainline_corpus`; `test_mi_spine` band declaration ≠ disk (`0049a`…`0049z` present, undeclared); `0084_silence_ledger.sql` declares `COUNSEL-GATED: no` where the test requires yes; DM-9 — a file outside `0038`/`0039`/`queries/closure_write.sql` touches `mainline.clause_blame_closure` executably. |
| I | **dangling references** | 3 | `deltalattice.yaml` cites three tests in `tests/unit/domain/lattice/test_red_first.py` that do not exist (the file was renamed to `test_lattice_red_first.py`, untracked); `0139_trg_candidate_project.sql` calls `mainline.fn_candidate_project`, *which the band never creates*; a recall claim-bound grep finds statements that restate the caveat differently. |
| J | **order-dependent** | 1 | `mainline-agentkit/tests/test_transport_residency.py::test_the_offline_path_imports_no_aws_sdk` fails in the full suite and **passes in isolation**. A test that depends on import order is a test that will lie eventually. |

### 3.5 CI cannot start — a referenced checker does not exist

`.github/workflows/ci.yml` job `checkers` ("every checker this lane invokes exists")
enumerates five programs and exits 1 if any is absent. **`scripts/qa/check_reuse.py` is
not on disk.** The other four are.

```
$ ./.venv/Scripts/python.exe scripts/qa/check_reuse.py
can't open file '…\scripts\qa\check_reuse.py': [Errno 2] No such file or directory
```

Every substantive job — `lockfile`, `format`, `types`, `imports`, `reuse`,
`hermetic-tests`, `sql-lint` — declares `needs: [checkers]`. **The entire pipeline is dead
on arrival at the first job.** The REUSE gate, therefore, is the one static check in this
report I could not run at all: the checker it names was never written.

### 3.6 `git clone` fails on Windows below a shallow directory

```
$ git clone D:/CoackroachDBxAWS/mainline <deep-path>
error: unable to create file verticals/mainline/apps/console/fixtures/bundles/blk-07/frames/
        GET~20~2Fv1~2Fclauses~2F…~2Fancestry~3Fas_of~3D5f91…e576.json: Filename too long
fatal: unable to checkout working tree
warning: Clone succeeded, but checkout failed.
```

Longest tracked path: **214 characters**, in the console's URL-encoded fixture bundles.
`core.longpaths` is unset. A clone into `D:/tc` succeeds cleanly (0 dirty files); a clone
into a path of ~60 characters or more does not. A judge on Windows who clones into
`C:\Users\<name>\Documents\projects\` gets a broken tree and no error they can act on.

---

## 4 · NOT BUILT

### 4.1 The proof, the QA harness and two whole distributions are UNTRACKED

`git status --porcelain` reports 58 paths. The untracked set is the finding:

```
?? scripts/proof/          ← gate_refusal.py — `just prove`, the entire product claim
?? scripts/qa/             ← doctor.py + all four QA checkers
?? qa/                     ← the ruff / mypy / test-state ratchets
?? conftest.py             ← the root conftest; --crdb wiring. Without it pytest cannot run
?? LICENSES/               ← the REUSE licence texts
?? packages/trappoint-testkit/                        ← a whole workspace distribution
?? verticals/mainline/packages/mainline-gate-svc/     ← a whole workspace distribution
?? verticals/mainline/packages/mainline-corpus/{pyproject.toml,README.md,src/…}
?? docs/HONESTY.md · docs/release/ · evidence/gate-refusal/ · tests/release/
?? .github/actions/ · .github/workflows/{cloud-verify,console,release-proof,supply-chain}.yml
?? .env.example · .github/dependabot.yml
```

Verified by cloning HEAD into a fresh directory:

```
$ git clone D:/CoackroachDBxAWS/mainline /d/tc && ls /d/tc/scripts
agents  custody  demo  grep_closure_readpath.py  mi_ratchet.py  recall
```

No `qa/`. No `proof/`. The clone's `README.md` is a different, older document with **no
"Four commands" section at all**, and its `justfile` has no `doctor` and no `prove`
recipe. **The four commands the README promises do not exist in the repository the README
would be read from.**

### 4.2 Five tables and their migrations

`mainline_ops.outbox`, `mainline.identity_assignment`, `mainline.patrol_run`,
`mainline_meas.agent_action`, `mainline_meas.standing`. Consumers written, producers
never. §1.1 and §1.5.

### 4.3 Migration `0207_v_safe_direction_current.sql`

Claimed by `directrix.yaml`, asserted by nine tests, absent from the tree.

### 4.4 `mainline.fn_candidate_project`

`0139_trg_candidate_project.sql` creates a trigger that calls it. The band never creates
the function. Caught by
`test_rc00_migration_shape.py::test_rc00g_a_trigger_function_only_names_columns_its_own_table_has`.

### 4.5 `scripts/qa/check_reuse.py`

Named by CI as one of five mandatory checkers. §3.5.

### 4.6 K2 evidence artefacts

`evidence/k2-checkpoint-cadence.json` and `evidence/k2-migration-attestation.json`. The
tests state the consequence themselves: *"the ~60 s window is an assumption"* and *"the
migration attestation chain has never been computed"* — the latter is now false in
substance (§1.2 computed it) and still true as an artefact.

---

## 5 · The judge's first five minutes, as measured

| step | working tree | fresh clone of HEAD |
|---|---|---|
| `git clone` | — | **fails on Windows** into any path ≳ 60 chars (§3.6) |
| README makes sense | yes — four commands, an honest caveat block, a link to `docs/HONESTY.md` | **no** — README is an older document with no command section |
| `just doctor` | `just` is not installed; `python scripts/qa/doctor.py` works | **file does not exist** |
| `just up` | compose is valid; note the running node is `mainline-crdb`, compose names it `trappoint-crdb`, so `just sql` targets a container that is not the one running | compose present |
| `just prove` | **works — exit 0, VERDICT PROVEN** (§1.3) | **file does not exist** |
| `pytest` | 8,066 pass / 44 fail | **cannot collect — no root `conftest.py`** |
| CI configured | 16 workflows, well structured, egress-hardened, `needs:` graph correct | **`ci.yml` untracked in part; `checkers` job fails on a missing file (§3.5)** |
| `just conform` | exit 1, `0/71` | same |

`README.md` is honest where it speaks. Its claim of *"246 of 261"* is **exactly right** —
I measured 246/261. Its claim that *"the fifteen that fail are enumerated"* is right. Its
claim that *"the conformance suite has not been demonstrated"* is right, and §2.1 puts
numbers on it. The README's failure is not honesty; it is that **it is not in the
repository.**

---

## 6 · What I would do next, in order

1. **`git add` the untracked set and commit.** Nothing else in this document matters to a
   judge until `scripts/proof/`, `scripts/qa/`, `conftest.py`, `qa/`, `LICENSES/`,
   `trappoint-testkit` and `mainline-gate-svc` are in the repository. This is the highest
   ratio of value to effort in the entire build.
2. **Write `mainline_ops.outbox`** into an allocation-legal band. §1.5 shows the exact
   column set and shows that it converts the proof from *refuse-with-a-caveat* to
   *refuse → dispose → admit, unassisted*, and takes the chain from 246 to 248.
3. **Write `scripts/qa/check_reuse.py`.** One missing file is holding the entire CI
   pipeline at zero.
4. **Fix `cases/_world.py::site_row`** (add `tenant_id`, `taxonomy_ver`, lower-case the
   `site_code`), then the `clause_version` builder behind it. That is the door between a
   corpus with 2 results and a corpus with results.
5. **Make `trappoint-conform` load its own cases** and probe capability tokens from the
   catalogue. A conformance CLI that cannot see 70 of its 71 implementations is not a
   conformance CLI.
6. **Decide the refusal-depth question with the number in hand.** Measured depth is 1 on
   both paths (§1.4). The pre-committed response is *cut the mechanism, do not ship it*.
   Either honour it, or amend the architecture's sentence to match the schema. Do not
   leave the claim standing unmeasured — it is the one place where this repository's
   prose currently outruns its evidence, and honesty is the moat.
7. Regenerate `migrations.lock.json`; write `0207` or delete the claim that it exists;
   add `__init__.py` to the colliding `tests/` directories.

---

## 7 · Reproducing every claim in this document

```bash
PY=./.venv/Scripts/python.exe
ADMIN='postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable'

# §1.1  the chain, via the real runner
docker exec mainline-crdb ./cockroach sql --insecure \
  -e "DROP DATABASE IF EXISTS proof_chain CASCADE; CREATE DATABASE proof_chain;
      ALTER DATABASE proof_chain CONFIGURE ZONE USING gc.ttlseconds = 4500;"
./.venv/Scripts/trappoint.exe migrate bootstrap --dsn '…/proof_chain'
./.venv/Scripts/trappoint.exe migrate up --dsn '…/proof_chain' \
    --tree mainline --migrations verticals/mainline/db/migrations

# §1.2  the attestation chain
./.venv/Scripts/trappoint.exe migrate attest --dsn '…/proof_chain'

# §1.3  THE GATE
$PY scripts/proof/gate_refusal.py --dsn "$ADMIN" --database proof_gate_final --keep

# §1.6  static gates
./.venv/Scripts/lint-imports.exe --config .importlinter
./.venv/Scripts/mypy.exe --config-file mypy.ini \
    packages/trappoint-migrate/src/trappoint_migrate \
    packages/trappoint-conformance/src/trappoint_conformance
./.venv/Scripts/trappoint.exe migrate lint \
    --root packages/trappoint-sql/refvertical/sql \
    --root verticals/mainline/db/migrations --root packages/trappoint-sql/templates

# §1.7 / §3.4  the suite
$PY -m pytest --crdb=none -q

# §2.1  the corpus as shipped
./.venv/Scripts/trappoint-conform.exe --profile mainline --list
./.venv/Scripts/trappoint-conform.exe --dsn '…/conf_mainline' --profile mainline

# §3.1–3.3  the red gates
./.venv/Scripts/ruff.exe check . ; ./.venv/Scripts/ruff.exe format --check .
./.venv/Scripts/mypy.exe --config-file mypy.ini $($PY scripts/qa/mypy_targets.py)
./.venv/Scripts/trappoint.exe migrate lock

# §4.1  the clone test
git status --porcelain ; git clone D:/CoackroachDBxAWS/mainline /d/tc && ls /d/tc/scripts
```

The unwelding harness (§1.4), the natural-path probe (§1.5), the outbox counterfactual
(§1.5) and the conformance census (§2.1) were written for this run and left in the
session scratchpad rather than committed, because they touch paths this agent does not
own. Each is described here in enough detail to be rewritten in under an hour, and each
reduces to primitives already in `scripts/proof/gate_refusal.py`
(`_prepare_database`, `apply_chain`, `seed_history`, `attempt_merge`, `force_counter`,
`sign_disposition`) plus `DROP TRIGGER permit_merge_gate ON mainline.permit` and
`ALTER TABLE mainline.permit DROP CONSTRAINT gate_closed_when_issued`.

---

**A truthful red is worth more than a fabricated green.** The gate is real; I broke it
open and it held where it claims to hold and gave way exactly where its own comments say
it gives way. The distance between this build and a defensible demonstration is a
`git add`, one seven-column table, one missing checker script, and a world builder that
knows what shape `mainline.site` is.
