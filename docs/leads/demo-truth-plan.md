<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# DEMO-TRUTH — wave plan

**Lead:** demo-truth · **Date:** 2026-08-13 · **Branch:** `master` · **HEAD at planning:** `2dc5c86`

The demo answers `200` and reports its own verdict as `NOT PROVEN`. That is the worst
failure mode available to us, because a judge may not notice. This plan closes it — and,
more importantly, closes the **class** of defect that produced it for the third time.

---

## 0 · What I measured before decomposing

Everything below was measured on this machine, at `2dc5c86`, not inherited from the brief.
Two of the brief's premises were **already false** and are recorded in `already_true`
rather than spent on a worker.

| Claim | Measured | Verdict |
|---|---|---|
| `testpaths` omits `verticals/*/apps/*` | `pyproject.toml:129-134` already lists `"verticals/*/apps/demo-api/tests"` | **already fixed** |
| demo-api tests are not collected | `pytest --collect-only -q` → **9653** collected; demo-api node ids present | **already fixed** |
| demo-api suite is 228 tests | `pytest verticals/mainline/apps/demo-api/tests --crdb=none -q` → **132 passed, 160 skipped = 292** | superseded |
| `gate_run` derives `487adc50…` | `sha256(b"credsigner")` = `487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765` | **confirmed** |
| `demo_world.sql` seeds `ff356d14…` | `sha256(b"mainline-demo/credential/demo.signer")` = `ff356d1461921438bbbc5d644db8793669cb948a46bddc2e8fb5ebef959bdf0c` | **confirmed** |
| the leak is two sites | `transitions.py:293-294` and `transitions.py:1032-1033`; no restore on any path | **confirmed** |
| Terraform publishes only `PERMIT_ID` | `infra/modules/demo-api/main.tf:154-155`; no `SIGNER_SUB`, no `COUNTERSIGNER_SUB` | **confirmed** |

### The finding the brief did not contain, and it is the load-bearing one

`testpaths` was fixed. Collection was fixed. **And the tests still do not run.**

```
$ pytest verticals/mainline/apps/demo-api/tests --crdb=none -q
132 passed, 160 skipped in 11.33s
```

Every CI pytest job in this repository runs `--crdb=none` (`ci.yml:471,487,522,634`).
Grepping all eighteen workflows for a pytest invocation **without** `--crdb=none` returns
only `boundary.yml` (AWS boundary tests) and `custody-chain.yml` (`trappoint-jcs`, a pure
library). **No CI job anywhere runs a cluster-backed demo-api test.**

So the 160 tests that would have caught beat 4 are collected, are green-adjacent, and are
`s`. Fixing `testpaths` moved the defect from *invisible* to *skipped*. That is progress
and it is not enforcement. **W7 exists because of this measurement**, and without W7 the
rest of this wave is theatre.

### The class, stated precisely

Five files define the demo signer's credential id. Four agree with each other and diverge
from the fifth — and the fifth is the only one that is actually deployed.

| # | Site | Value |
|---|---|---|
| 1 | `gate_run.py:576,578` | `_sha("cred","signer")` |
| 2 | `transitions.py:971,973` | `_sha("cred","signer")` |
| 3 | `tests/conftest.py:360` | `_sha("cred","signer")` |
| 4 | `scripts/proof/gate_refusal.py:844,1441` | `_sha("cred","signer")` |
| 5 | **`db/seeds/demo/demo_world.sql:124,132`** | `digest('mainline-demo/credential/demo.signer','sha256')` |

`conftest._seed` (line 351) builds an entire **parallel world** — `w3_site`, `w3.signer`,
`w3.countersigner` — using the same `_sha` helper the code under test uses. The test and
the code agree because they read the same constant. Neither has ever met
`demo_world.sql`, which is what `scripts/deploy/seed_demo.py:115` actually applies to the
cloud (`SEED_FILES = ("demo_world.sql", "demo_permit.sql")`).

This is the identical shape as the permit-id near-miss and the `dict_row` 500. **A test
that cannot disagree with the code it tests proves nothing.**

---

## 1 · The beat-4 decision, on the merits

Two reconciliations are available and **both are wrong**:

- **Change `demo_world.sql` to seed `sha256("credsigner")`.** Rejected. It makes a
  *database fact* imitate an *application constant*. It also breaks the seed's own naming
  scheme — every other digest in that file is `digest('mainline-demo/<kind>/<subject>')`
  (cose, aaguid, competency, commit ids) — for exactly one row. And `"cred"+"signer"` is
  not parameterised by `signer_sub` at all, so a second signer would need a second
  ad-hoc string. Smaller diff; worse repository.
- **Change `gate_run` to compute `sha256("mainline-demo/credential/" + signer_sub)`.**
  Rejected. It is still a second definition of the same rule, and it hardcodes *the demo
  seed's* naming convention into shipped application code. The `w3` fixture world, the
  conformance world, and any real enrolment all break again. **Same class, new instance.**

**DECISION — resolve it, do not derive it.**

`signer_credential_id` is a **foreign key into `mainline.signing_credential`**
(`0066_disposition.sql`). The FK exists precisely because the credential is an
authoritative row that the database owns. In the real product a credential id comes from
WebAuthn enrolment and is *not derivable by anybody*. Application code deriving a value
whose authority lives in a table is the defect; the digest mismatch is only how it
surfaced.

So the demo-api will **look the credential up by `signer_sub`**:

```sql
SELECT credential_id FROM mainline.signing_credential
 WHERE signer_sub = %s AND revoked_at IS NULL
```

This is chosen on the merits, not on diff size — it is a larger change than either
alternative. It is right because:

1. it makes the code correct against **any** seed: `demo_world.sql`, the `w3` fixture, a
   customer's real enrolment;
2. it removes definition sites 1–4 entirely, leaving **one** definition (the seed row) —
   which is what "close the class" means for this constant;
3. it converts a `23503` fired deep inside beat 4's savepoint into an explicit,
   diagnosable refusal at resolve time that **names the missing `signer_sub`**;
4. `scripts/deploy/capture_demo_bundle.py:929-937` already reads
   `signing_credential` by `signer_sub` and refuses a bundle when a row is missing. The
   deployment tooling already treats the table as authoritative. The application was the
   outlier.

The reasoning is recorded permanently in `docs/demo/beat4-credential-authority.md` (W8),
including both rejected options, so the next wave cannot re-litigate it from scratch.

---

## 2 · The autocommit leak

`db.py:306` opens the shared module-scope connection with `autocommit=True`.
`health.py:106` documents that assumption in prose. Two functions break it and never
restore:

- `transitions._prepare` (`:293-294`) — called from `:513, :669, :760, :931`
- `transitions._demo_gate_run` (`:1032-1033`)

`handle_transition` (`:1069`) has `except` arms that `conn.rollback()` — which ends the
transaction but leaves `autocommit` **False**. The next invocation on a warm Lambda
inherits a session that opens an implicit transaction on its first read.

The existing test is the class again:

```python
def test_gate_run_leaves_the_connection_usable(w4_conn) -> None:
    handle_transition("demo_gate_run", {}, {}, w4_conn)
    assert w4_conn.execute("SELECT 1").fetchone() == (1,)  # passes INSIDE a transaction
```

`SELECT 1` succeeds in autocommit and in an open transaction alike, and `w4_conn` is
per-test so nothing is ever inherited. **The assertion cannot fail for the reason the test
was written.** W5 replaces it with one that observes `conn.autocommit` and
`conn.info.transaction_status` directly and drives two requests down one connection.

---

## 3 · Worker map

Paths are **strictly disjoint and literally enumerated**. No worker may touch a path it
does not own; a needed change outside its list is reported to the lead, not made.

```
W1  credentials.py (new) + gate_run.py            ─┐
W2  transitions.py + health.py                     ├─ the fix
W6  infra/modules/demo-api/*, infra/envs/demo/*   ─┘

W3  tests/conftest.py  (seed from demo_world.sql) ─┐
W4  constant_agreement checker + gate_refusal.py   ├─ the class
W5  connection-hygiene + transition tests          │
W7  cluster-backed CI job + pyproject testpaths   ─┘

W8  acceptance re-run, decision record, evidence  ─── the verdict
```

| Worker | Owns | Depends on |
|---|---|---|
| W1 | `credentials.py`, `gate_run.py`, `tests/test_credentials.py` | — |
| W2 | `transitions.py`, `health.py` | W1 |
| W3 | `tests/conftest.py` | — |
| W4 | `scripts/demo/constant_agreement.py`, `tests/demo/test_constant_agreement.py`, `scripts/proof/gate_refusal.py`, `evidence/demo/constant-agreement.json` | W1 |
| W5 | `tests/test_transitions.py`, `tests/test_connection_hygiene.py` | W2, W3 |
| W6 | `infra/modules/demo-api/{main.tf,variables.tf,README.md}`, `infra/envs/demo/{main.tf,variables.tf,terraform.tfvars.example}` | — |
| W7 | `.github/workflows/demo-api.yml`, `pyproject.toml`, `verticals/mainline/apps/demo-api/pyproject.toml` | W3 |
| W8 | `docs/demo/beat4-credential-authority.md`, `evidence/deploy/acceptance.json`, `evidence/demo/beat4-live.json` | W1–W7 |

### Cross-lead hazard — flagged, not resolved here

**BLOCKER 2 (the bill) is not this lead's scope**, but the cost lead will edit
`infra/modules/demo-api/main.tf` and `variables.tf` for `timeout`, `memory_size`,
`reserved_concurrent_executions` and the response cap. **W6 owns those two files in this
wave.** The orchestrator must serialise the two leads on those paths or merge them into
one worker. Do not let two waves write the same `.tf` concurrently.

---

## 4 · Rules binding every worker

- **NEVER `terraform apply`.** `init` / `validate` / `plan` / `show` only.
- **NEVER print a credential** into output, a file, or a structured result.
- **NEVER weaken `docs/HONESTY.md`, `docs/CI-STATE.md`, a ratchet, or an assertion to
  gain a green.** `continue-on-error` and `|| true` are banned.
- **NEVER edit recorded evidence to silence a checker.** Fix the checker.
- No TODOs. Fix causes, never symptoms. File ownership is absolute.
- Windows: `PYTHONPATH` separator is `;`; interpreter is
  `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`.
- Local cluster: `postgresql://root@localhost:26257/defaultdb?sslmode=disable`
  (`trappoint-crdb`, pinned v26.2.5). CockroachDB Cloud needs a **40001 retry loop**.
- `CREATE SEQUENCE` / `nextval` / `SERIAL` / `unique_rowid()` are **BANNED**; `FAMILY` is
  reserved.
- `scenario.py`, `gate_run.py`, `transitions.py` are **already factory-agnostic** via
  `scenario.positional()`. Do not re-fix that.

---

## 5 · What "done" means for the wave

1. Beat 4 admits against a database carrying **`demo_world.sql`**, through the real
   handler, under the environment Terraform publishes.
2. The demo-api suite's cluster-backed tests **run against `demo_world.sql`** and a
   divergence between code and seed is a **failing test**, not a 500 in front of a judge.
3. Those tests **execute in CI against a real cluster** — not collected, not skipped: run.
4. No constant load-bearing for a demo beat is defined in two places, and that is
   **enforced mechanically** by a checker that fails the build.
5. A connection is returned to `autocommit=True` on every path, including the exception
   path, and a test fails if a later request inherits a dirty one.
6. `MAINLINE_DEMO_SIGNER_SUB` and `COUNTERSIGNER_SUB` are published by Terraform.
   `SITE_ID` is **left alone** — measured not load-bearing.
7. The acceptance transcript is re-run against the real handler on the deployed seed and
   committed. **It reads `PROVEN` honestly or it stays `NOT PROVEN`.** It is never
   relaxed to reach a green.
