<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Demo correctness — the plan, written after measuring, not before

**Lead:** demo-correctness. **Written 2026-08-13 on TRAPPOINT, against `master` at `86b25bd`.**
Every number below was produced by a command run in the same sitting as this file. Nothing is
carried forward from a recorded board.

---

## 0. What I measured before decomposing

Four of the things the brief asks for are **already true**, and one thing the brief does not
mention is **worse than anything it does**. Both are recorded here before the work is split,
because a wave that spends a worker re-doing a finished task is a wave that did not measure.

### 0.1 The one-line defect is real and reproduced

```
$ .venv/Scripts/python.exe -c "... psycopg.connect(..., row_factory=dict_row) ..."
DESCRIPTION NAMES: ['explain_refusal']
shape {'explain_refusal': {}}   row[0]? KeyError: 0
```

`refusal.py:235` reads

```python
return (row[0] if row and isinstance(row[0], dict) else None), None
```

`_explain` runs `SELECT trappoint.explain_refusal(%s, %s, %s, %s)`. CockroachDB names that
single column `explain_refusal`. `db.py:309` opens every production connection with
`row_factory=dict_row`, so the row is a plain `dict` with one key and `row[0]` is
`KeyError: 0`. The short-circuit does not save it: `row and isinstance(row[0], dict)`
evaluates `row[0]` to test it.

It is reached by `gate_run._record_refusal` on beats 2 and 3 of **every** gate run and by
`transitions._refused` on **every** kernel refusal. `evidence/deploy/acceptance.json` records
the consequence verbatim: two `500 … internal_error · resource=demo_gate_run · KeyError: 0`
and the verdict `NOT PROVEN`.

### 0.2 THE FINDING THE BRIEF DID NOT CONTAIN — the demo-api suite has never run

```
$ pytest --collect-only -q                                   →  9324 tests collected
$ pytest verticals/mainline/apps/demo-api/tests --collect-only -q  →   228 tests collected
```

Those 228 are **not** among the 9324. `pyproject.toml:85` declares

```toml
testpaths = ["tests", "packages", "verticals/*/packages/*/tests"]
```

and `verticals/mainline/apps/demo-api/tests` matches none of the three. `verticals/*/packages/*/tests`
resolves to four directories, all of them under `verticals/mainline/packages/`. The app's tests
live under `verticals/mainline/apps/`.

This is the same defect class the comment directly above that declaration describes and claims
to have fixed on 2026-08-10 — the tree grew and the declaration did not — and it was fixed for
`verticals/*/packages/*` while leaving `verticals/*/apps/*` behind.

**This is the real answer to brief item (b).** A previous wave wrote
`tests/test_row_factory_contract.py` — 627 lines, both factories, an AST ratchet, an explicit
`_REFUSAL_BLOCKER` diagnosis naming `refusal.py:235` — and that file **has never executed in
CI or in a default `pytest` invocation**. The contract that would have caught the 500 was
written, committed, and never collected. Making the three modules factory-agnostic without
making their test run is remembering, not enforcing.

Basename-collision check before proposing the change: all seven demo-api test modules have
globally unique basenames across `tests/`, `packages/` and `verticals/`. No collision.

### 0.3 The migration count — the truth, established

`/v1/health` reports `migrations_applied` from
`SELECT count(*) FROM trappoint.schema_migration WHERE state = 'applied'` (`health.py:77-79`).

Two appliers exist and they write **two different ledgers**:

| applier | writes | used by |
|---|---|---|
| `trappoint migrate up` | `trappoint.schema_migration` (the only `INSERT` into it in the tree, `trappoint_migrate/runner.py:295`) | nothing that built `mainline_demo` |
| `scripts/deploy/cloud_chain.py` | `trappoint.deploy_chain` — one marker row carrying `files`, `applied`, `failed`, `retried`, `tree_fingerprint`, `live_fingerprint` (`cloud_chain.py:194-211`) | **this is what built `mainline_demo`** |

So `0` is a **true count of the wrong ledger**. The chain really is applied — the non-null
`schema_fingerprint` the same statement returns is written by `trappoint migrate bootstrap`
and moves when the schema moves.

`scripts/deploy/demo_acceptance.py:573-601` already reasons this out correctly, as an
advisory. **The endpoint itself still says a bare `0` and nothing else**, and the endpoint is
what a judge reads. The fix is not to fake a number: it is for `/v1/health` to read **both**
ledgers and name which one it is quoting.

One stale claim to correct in passing: `test_reads.py:691` asserts in prose that "the deployed
cluster is migrated by W2 with the real command and reports 271." It is not, and it does not.

### 0.4 The near-miss — where the guard actually stands

`transitions._demo_guard` (`transitions.py:261`) arms only when `subject_id == scenario.permit_id`,
and `scenario.permit_id` comes from `scenario.from_env()`, which reads `MAINLINE_DEMO_PERMIT_ID`
and **falls back to `demo_uuid("permit")`** — the uuid5 derivation nothing has ever seeded.

The Terraform side is fixed and committed: `infra/modules/demo-api/variables.tf:250` defaults
`scenario_permit_id` to `dec0de00-0006-4000-8000-000000000001`, and `main.tf:131-132` publishes
it under **both** `MAINLINE_SCENARIO_PERMIT_ID` and `MAINLINE_DEMO_PERMIT_ID` — the second
being the name `from_env` actually reads.

**The residual defect is the fallback itself.** The guard is armed by an environment variable
and disarmed by its absence. A deploy that drops that variable — a `terraform apply` from a
different tfvars, a hand-edited Lambda config, a `sam local` — silently re-opens exactly the
hole the audit found, and nothing anywhere would say so. `authorization_type = NONE` on the
Function URL means the caller is anonymous by design, so the guard is the only thing between
that caller and four irreversible committing POSTs (`merge_permit`, `suspend_permit`,
`materialise_checks`, `sign_disposition`) against a DSN role holding the matching UPDATE and
EXECUTE grants.

Two existing tests assert the 423 (`test_transitions.py:381`, `test_row_factory_contract.py:598`),
and **both set `MAINLINE_DEMO_PERMIT_ID` themselves first**. Neither could have caught the
near-miss. Neither would catch it now.

### 0.5 The suppression pair

`.github/workflows/submission.yml` carries the only real suppressions left in the tree:
`continue-on-error: true` at lines **148, 155 and 172**, and `|| true` at line **176**. Every
other hit in `.github/workflows/` is a comment recording a removal, or a `docker rm -f … || true`
teardown, or a `grep -c` whose exit-1-on-zero is arithmetic rather than a swallowed verdict.

---

## 1. What is already true — do not spend a worker on these

1. **`scenario.py`, `gate_run.py`, `transitions.py` are already factory-agnostic.** Every
   statement routes through `scenario.positional()`, which sets `row_factory=tuple_row` on the
   **cursor**, never mutating the connection. 21 call sites. `refusal.py` is the only module in
   the package that still reads a row it did not shape.
2. **`tests/test_row_factory_contract.py` already exists and is good.** Both factories, then
   equality on everything that is a function of what the database said; the measured
   demonstration that name-keyed access was *not* the fix (`_FINGERPRINT_SQL` returns ten
   columns CockroachDB all names `count`); and an AST ratchet banning `conn.execute(…).fetchone()`
   in those three modules. It needs to be **extended and collected**, not written.
3. **The permit-id fix is landed in Terraform.** `variables.tf:250` = `dec0de00-…0001`, published
   under both env names, with a validation block. Verified against the committed tree.
4. **The migrations root cause is already correctly reasoned** in `demo_acceptance.py:573-601`.
   The analysis does not need redoing; the *endpoint* needs to carry it.
5. **`ruff format` is clean.** The local "249 files" is a CRLF artefact. **No format commit.**

---

## 2. The eight workers

Ownership is absolute and literally enumerated. No path appears twice.

| # | worker | owns | depends on |
|---|---|---|---|
| W1 | the `KeyError`, at its cause | `refusal.py`, `test_refusal_row_factory.py`, `rowfactory-defect.json` | — |
| W2 | the ratchet, package-wide and repo-wide | `test_row_factory_contract.py`, `scripts/qa/row_factory_ratchet.py`, `tests/unit/test_row_factory_ratchet.py` | W1 |
| W3 | collection — make the suite exist | `pyproject.toml`, demo-api `conftest.py`, `docs/ci/test-collection.md` | — |
| W4 | the legacy suite onto the production path | `test_gate_run.py`, `test_routes_gate_run.py`, `test_envelope.py`, `test_static_site.py` | W1 |
| W5 | `migrations_applied`, made honest | `health.py`, `test_reads.py`, `migrations-ledger.json` | — |
| W6 | the guard, armed, and proven against an anonymous caller | `transitions.py`, `test_transitions.py`, `test_demo_guard_anonymous.py`, `demo-guard-armed.json` | W1 |
| W7 | the acceptance transcript, re-run for real | `acceptance.json`, `demo_acceptance.py`, `local_furl.py` | W1, W5, W6 |
| W8 | the suppression pair, and the board | `submission.yml`, `demo-health.yml`, `CI-STATE.md`, `HONESTY.md` | W1–W7 |

### The one coupling that is not negotiable

**W1 and W6 land together or not at all.** W1 removes the accident that makes the anonymous
write surface inert. W6 is the guard that must be load-bearing before that accident is gone.
Neither may be committed without the other on the same commit. This is the whole lesson of the
near-miss, stated as a merge rule.

---

## 3. Rules binding on every worker

* **Never run `terraform apply`.** `init`, `validate`, `plan`, `show` and read-only AWS calls
  only.
* **Never print a credential** — not into a file, not into a structured result, not into a log.
  DSNs are read from the repo-root `.env` and redacted through `db.redact`.
* **Never weaken `docs/HONESTY.md`, `docs/CI-STATE.md`, a ratchet or an assertion to gain a
  green.** `continue-on-error` and `|| true` are banned; W8 removes the last pair.
* **Never edit a recorded transcript to silence a scanner.** `evidence/deploy/acceptance.json`
  is regenerated by re-running the prover against the real handler (W7), never by hand.
  If it still says `NOT PROVEN` after a real run, it stays `NOT PROVEN` and W8 records why.
* **No TODOs. Fix causes, not symptoms.** Every new file carries an SPDX header — `reuse`
  is a CI lane.
* **Measure on the production path.** A test that connects with psycopg's default `tuple_row`
  proves nothing about a Lambda that opens `dict_row`. That mistake is what this wave exists
  to close.
