<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# CI-floor lead — the plan, written after measuring, not before

**Date** 2026-08-13 · **HEAD** `2dc5c86` · **Lead** ci-floor

Everything below was measured on this tree today, with a warm board: thirteen stale
lanes were dispatched at `2dc5c86` and read back before a single worker was written.
Nothing here is copied from a recorded board.

---

## 0 · The headline: seven of the eight assigned tasks are already true

The brief assigned (a)–(h). Measured, (a), (b), (c), (d), (e), (f), (g) and most of (h)
are **already done** — landed by the two waves that ran before this one. Spending eight
workers re-doing them would have been eight workers of churn. The evidence is in §1.

What is actually red is a **different and smaller set**, and it is now §2.

---

## 1 · Already true — measured, with the command that measured it

| # | Assigned task | Measurement | Verdict |
|---|---|---|---|
| a | restore `canon_v1.py` to `260ed37d`, fence it from the formatter | `git show HEAD:…/canon_v1.py \| sha256sum` → `260ed37d…d659`; worktree bytes identical raw **and** LF-normalised; `ruff.toml [format] exclude` names **both** copies with the incident written out above it | **DONE** |
| b | the 10 genuinely unformatted files | `git archive HEAD` → clean LF export → `ruff format --check .` → **`1456 files already formatted`, zero to reformat**. CI job `ruff format · the counted lint ratchet` is **green** at HEAD | **DONE** |
| c | `bedrock_backend.py` — 22 ruff + 4 mypy | `ruff check …/bedrock_backend.py --statistics` → no output, exit 0. `mypy …/bedrock_backend.py` → `Success: no issues found`. CI job `mypy · and the target list is complete` **green** | **DONE** |
| d | `SEC-ACCOUNT-ID` stops firing on `322122547200` | `scripts/aws/verify_evidence.py` → **`896 assertions across 40 of 40 declared invariants. PASS`**, of which `SEC-ACCOUNT-ID` contributes **114**. `aws-evidence` lane **green**, mutation family included | **DONE** |
| e | DM-9 — two files, three sites | `scripts/grep_closure_readpath.py` → **16 allowlisted, 0 violations, exit 0** | **DONE** (label audited in W8) |
| f | RESTATED census riser at `assert_gate_refuses.py:67` | census code lifted verbatim out of `db.yml` and run on the LF export → **FLOATING 0 / ceiling 0 (held), RESTATED 19 / ceiling 19 (held)**. `assert_gate_refuses.py` does not appear in the list at all | **DONE** |
| g | remove `submission.yml` suppressions | zero live `continue-on-error`, zero live `\|\| true` in the file — every remaining grep hit is a comment recording the removal. `submission` lane **green** | **DONE** |
| h₂ | `judge cli.py envelope` prints eleven "ok" and exits 0 | `judge-pack.yml` carries an **`envelope-teeth`** job that plants three real mutations (`REQUEST_TIMEOUT_SECONDS 20→25`, `MAX_RESPONSE_BYTES 10240→10241`, and the absent-`mainline_mcp` case) and requires `--require-cross-check`. `judge-pack` **green** | **DONE** |
| h₁ | the image-pin assertion never asks the server its version | `cloud-verify.yml`, `custody-chain.yml` and `db-schema.yml` each run `SELECT version()` against the started node and compare it to the pin, and each carries an **`image-pin-bites`** negative control on a neighbouring tag. `custody-chain`'s *"the version comparison bites — a neighbouring tag must fail it"* job is **green** | **DONE in three lanes**; `db.yml` unaudited → W8 |
| — | `testpaths` excludes `verticals/*/apps/*`; `test_row_factory_contract.py` has never run | `pyproject.toml` now carries `verticals/*/apps/*`; `pytest --collect-only` counts **15** `test_row_factory_contract` items in the default run | **DONE** |

**Do not re-open any row above.** Two waves running have found assigned work already
done; this is the third. A worker sent at a green is a worker spent churning a file.

---

## 2 · The board, warm, at `2dc5c86`

Thirteen lanes dispatched today and read back; four had already run on the push.

**GREEN (11):** `aws-evidence` · `submission` · `supply-chain` · `skills` ·
`release-proof` · `judge-pack` · `cloud-verify` · `claims` · `boundary` · `console` ·
`mutation-ratchet`

**RED (6):** `ci` · `schema` · `db` · `db-schema` · `demo-health` · `custody-chain`

Of the six reds, **four are honest and stay red**, and their messages are already
sharp enough to quote:

- **`db` / `ci`→`PL-2`** — the ADR asks for the URL of a `db` run in which the
  CONFORMANCE step itself went red. CONFORMANCE has **never executed**: `db.yml` stops
  one step earlier at `0058_blocking_check` on the missing `trappoint_ref.event`
  producer. Recording any other red `db` run is the exact laundering the field exists to
  prevent. Stays `UNRECORDED`.
- **`demo-health`** — `docs/submission/SUBMISSION.json:demo_url = UNRESOLVED`. Red
  because the demo is not deployed, not because the lane is broken; the step prints the
  eight assertions that went unmeasured and the `-f url=` dispatch that falsifies it.
- **`custody-chain` / "a stranger verifies the bundle"** — `16 checks | 9 passed |
  0 failed | 7 not checked`, each of the seven naming the module that does not exist and
  the owner (`verify-crypto`).
- **`schema`, `db-schema`** — the model reds, declared in their own headers.

**The one red that is NOT honest is `ci`**, and it is the whole of §3.

---

## 3 · Why `ci` is the only dishonest red, and what that costs

`ci.yml` splits pytest into two jobs whose colours are supposed to mean different
things — and the file says so in its own summary:

> `pytest --crdb=none` runs everything EXCEPT the assertions this repository declares
> red-by-design, so **a red there is a regression and nothing else**.

Measured at HEAD that job reports `8 failed, 8629 passed, 1003 skipped, 13 deselected`.
**Five of the eight are not regressions.** They are declared incompleteness that has
leaked into the lane that means "regression", which destroys the only distinction the
two jobs exist to draw. A reader who trusts the sentence above is being misled, and
the repository is public.

The eight, measured:

| # | Test | What it actually is |
|---|---|---|
| 1 | `test_k2_exit.py::test_k2_1_tamper_is_caught_by_a_consistency_proof` | `evidence/CUSTODY_ATTACK_MATRIX.md` does not record A1 → check 3. **Closeable by running the producer** |
| 2 | `test_k2_exit.py::test_k2_2_closure_rewrite_is_caught_by_check_14` | same matrix, A10 → check 14. **Closeable by running the producer** |
| 3 | `test_k2_exit.py::test_k2_4_checkpoint_cadence_measured_and_deadman_defined` | `evidence/k2-checkpoint-cadence.json` — **no producer names the path** |
| 4 | `test_k2_exit.py::test_k2_5_checkpoint_wire_format_tagged_v1_0_with_changelog_entry` | **one line** in `spec/CHANGELOG.md`. The other half is already green |
| 5 | `test_k2_exit.py::test_k2_6_migration_attestation_chained_with_a_stable_fingerprint` | `evidence/k2-migration-attestation.json` — `mainline_custody_patrol` not importable |
| 6 | `test_live_cassettes.py::test_every_recorded_body_hashes_to_its_index_row` | a recorded body hashes `11d32dd3…` against an index row saying `136eec34…`. **A real integrity failure** |
| 7 | `test_envelope.py::test_no_web_framework_or_aws_sdk_is_imported` | the deployment package pulled in `['boto3','botocore','httpx','pydantic']`. **A real packaging failure**, and it is the same package the bill argument is made about |
| 8 | `test_response_contract.py::test_the_one_unmeasured_response_is_bounded_by_construction` | `OSError: [Errno 36] File name too long` — the test builds a >255-byte path component. **The test is broken, so the response cap is currently unasserted** |

Note what #8 means. The 2 MiB response cap is the one the verifier measured
**NON-BINDING** — it refuses 0 of 75 served objects, the largest 1,554,168 B — and the
only test that would have caught that dies on an `OSError` before it asserts anything.
A test that cannot reach its assertion is the same lie as a test that cannot disagree
with its code. That is the class this wave was told to close, in a second costume.

---

## 4 · Also real, found by the verifier, and still unowned

`transitions._prepare` (`transitions.py:293-294`) and `_demo_gate_run` (`:1032-1033`)
both do

```python
if conn.autocommit:
    conn.autocommit = False
```

on the **shared module-scope connection** and never restore it, while `db.py:306` opens
with `autocommit=True` and `health.py:106` documents that assumption in prose. Measured
present at HEAD. On a marker-less database this is a hard **503 `[25P02]`** on the very
next request after any gate-run. It is W7.

---

## 5 · The eight workers

Ownership is absolute and the paths are literal. No worker touches a file another
worker owns.

| id | title | files |
|---|---|---|
| W1 | the attack matrix is generated from a run, not from prose | 4 |
| W2 | K2's three unclosable criteria stop pretending to be regressions | 2 |
| W3 | the live cassette index tells the truth about its bodies | 3 |
| W4 | the response cap binds, and the test can reach its assertion | 2 |
| W5 | the deployment package contains what the envelope says it contains | 2 |
| W6 | the demo test runs against the seed the cloud actually carries | 3 |
| W7 | the shared connection is handed back the way it was borrowed | 2 |
| W8 | anti-vacuity audit, and CI-STATE rewritten to the measured board | 4 |

W8 runs last and depends on all seven.

---

## 6 · Standing rules for every worker

1. **Measure before you fix.** Three waves running have found assigned work already
   done. If your target is already true, say so and stop — do not churn the file.
2. **A green that cannot fail is a lie told in CI, and this repository is public.**
   Every assertion you write or repair must be shown falsifiable: plant a violation,
   watch it go red, remove the plant. If you cannot make it falsifiable, name it
   unproven in `docs/CI-STATE.md` rather than counting it.
3. **Never weaken `docs/HONESTY.md`, `docs/CI-STATE.md`, a ratchet or an assertion to
   gain a green.** `continue-on-error` and `|| true` are banned and the repository
   currently has none.
4. **Never edit recorded evidence to silence a checker.** Regenerating an artefact by
   running its producer is not editing it; hand-writing a value into it is.
5. **No `terraform apply`.** `init` / `validate` / `plan` / `show` and read-only AWS
   calls only.
6. **Never print a credential** into output, a file or a structured result.
7. **No TODOs.** Fix causes, never symptoms.
8. Platform: CockroachDB v26.2.5, local `trappoint-crdb` at
   `postgresql://root@localhost:26257/defaultdb?sslmode=disable`. Python is
   `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`; the Windows `PYTHONPATH`
   separator is `;`. `CREATE SEQUENCE` / `nextval` / `SERIAL` / `unique_rowid()` are
   banned; `FAMILY` is reserved.
9. **`ruff format --check` on Windows reports ~223 files. That is a CRLF artefact and
   it is not yours.** The committed tree is clean: measure on a `git archive HEAD`
   export, never on the Windows working tree.
10. **CI logs expire.** Dispatch and read warm; never trust a recorded board.
