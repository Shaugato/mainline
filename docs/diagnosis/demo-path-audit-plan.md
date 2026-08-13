<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# DEMO-PATH AUDIT — plan for 10 read-only analysts

Lead: demo-path-audit lead. Written 2026-08-13 after a scoping pass that **ran the real
handler**, not read it. Every number below was measured on this machine today; the commands
are given so an analyst can re-run them rather than trust them.

---

## 0 · THE RULE THAT OVERRIDES EVERYTHING ELSE IN THIS FILE

**You are READ-ONLY. A separate 24-worker wave is editing this repository RIGHT NOW.**

* Do **not** edit, create, delete, format, or `git`-mutate any file in the repo **except the
  ONE file assigned to you** under `docs/diagnosis/`.
* Do **not** run `git add|commit|checkout|stash|restore`, formatters, `--fix` linters, or
  codemods. Do **not** run `terraform apply` or any mutating AWS call.
* Do **not** print a credential into your output or into your file.
* You **may** read anything, run read-only SQL, run `pytest`, run `terraform plan/validate/show`,
  run read-only `aws`/`gh`, and create scratch databases on the LOCAL node only.
* `git status` already shows 11 modified and 7 untracked paths (`gate_run.py`,
  `transitions`' test conftest, `credentials.py`, `infra/**`, `scripts/deploy/**`). **Files
  under your feet will change mid-session.** Timestamp every quotation: record the command,
  its output, and `git rev-parse HEAD` at the moment you ran it. If a file changes between
  two of your observations, say so rather than silently re-reading.
* Your deliverable is **evidence and analysis, not a fix.** Naming a defect precisely — with
  the exact `file:line` on **each side** of the divergence, the command, the real output, the
  failure a judge would see, and an honest severity — is worth more than fixing it.
* **A clean slice is a real result.** If your area holds nothing, say so plainly. Inventing
  findings to look busy is the worst possible outcome here.

---

## 1 · WHY THIS WAVE EXISTS

Three adversarial rounds each returned NO-GO, and each found a defect the previous round
could not have seen. All three had one shape:

> **A test agrees with the code because both draw on the same constant or the same
> convenience path, and both diverge from what is ACTUALLY DEPLOYED.**

The permit-id near-miss (guard armed at a uuid5 nothing seeded), the `dict_row` 500 (tests
connected with `tuple_row`), the beat-4 signer FK (291 green tests, none against
`demo_world.sql`). Fixing one per round does not converge. **This wave finds everything at
once** so a single following wave can fix a complete list.

**Therefore: run it. Do not read it.** Every prior defect was found by executing the real
handler against the real seed. Anything you could only reason about must be labelled
`REASONED, NOT RUN` in your file, with the reason it could not be run.

---

## 2 · WHAT IS ALREADY KNOWN — do NOT spend an analyst re-deriving these

Closed, verified, or accepted by the founder. Re-deriving these is wasted budget.

| # | Fact | Status |
|---|---|---|
| 1 | Terraform: 11 to add, 44/44 preconditions, `reserved_concurrent_executions = -1`, zero drift | known |
| 2 | Anonymous callers cannot mutate: four 423s through the real handler; lane falsifiable | known, **and I re-confirmed it today — see §4.4** |
| 3 | Gate proof PROVEN caveat-free: chain 271/271, PROJECTION 10/10, REFUSAL `23514`, DRIFT `P0001`, ADMISSION `00000` | known, **re-confirmed today on a fresh `demo_world.sql` seed — §4.3** |
| 4 | CI 11 green / 17; `custody-chain` 7/16, `schema`, `demo-health` are intentional-and-correct reds | known |
| 5 | Canon drift: 998c526 added 4 blank lines; registry pin `260ed37d` is right | known |
| 6 | `ruff format`: exactly 10 real files; other 234 are a CRLF artefact | known |
| 7 | `SEC-ACCOUNT-ID` false-positives on `322122547200` = 300 GiB in bytes | known |
| 8 | Cost worst case USD 33,250/30d, bounded by an unchosen account concurrency quota of 10. Founder chose **"bounded but open"** — no auth on the URL, real limits in code | **a decision, not a defect. Do not re-argue it.** |
| 9 | `transitions._prepare` / `_demo_gate_run` set `conn.autocommit = False` on the shared connection and never restore it | known — **W6 owns proving what it actually costs** |
| 10 | Platform: Cloud `mainline_demo` Basic, aws-ap-southeast-1, needs a 40001 retry loop; vector index only when hinted; `SEQUENCE`/`SERIAL`/`unique_rowid()` banned; `FAMILY` reserved; Bedrock ap-southeast-2 | known |
| 11 | `testpaths` at `pyproject.toml:129-134` **now** includes `verticals/*/apps/demo-api/tests` | **the concurrent wave already fixed this.** Verify collection, do not re-report the old state |
| 12 | The permit-id near-miss is closed: `infra/modules/demo-api/variables.tf:275` `default = "dec0de00-0006-4000-8000-000000000001"` | fixed |

---

## 3 · THE ENVIRONMENT EVERY ANALYST SHARES

### 3.1 What Terraform actually publishes to the function

Read from `infra/modules/demo-api/main.tf:135-200` and `infra/envs/demo/main.tf:290-320`.
This is the environment your probes must reproduce. Anything you test under a *different*
environment is not a test of the deployment.

| Env var | Source | Effective value |
|---|---|---|
| `MAINLINE_DSN_PARAM` | `local.dsn_parameter_path` | SSM SecureString **name**; the DSN itself is never in state |
| `MAINLINE_DSN` | **not set by Terraform** | absent in the deployment — `db.resolve_dsn` goes to SSM |
| `MAINLINE_DEMO_DATABASE` | `var.demo_database` | declarative only; handler takes the DB from the DSN |
| `MAINLINE_SCENARIO_PERMIT_ID` | `var.scenario_permit_id` | `dec0de00-0006-4000-8000-000000000001` — **read by nothing** |
| `MAINLINE_DEMO_PERMIT_ID` | `var.scenario_permit_id` | `dec0de00-0006-4000-8000-000000000001` — **the one `scenario.from_env` reads** |
| `MAINLINE_DEMO_SIGNER_SUB` | `var.demo_signer_sub` | `demo.signer` |
| `MAINLINE_DEMO_COUNTERSIGNER_SUB` | `var.demo_countersigner_sub` | `demo.countersigner` |
| `MAINLINE_DEMO_SITE_ID` | **deliberately absent** | falls back to `demo_uuid("site")` = `c333eb17-…` — **which is NOT the seeded site `dec0de00-0001-…`.** Argued inert at `variables.tf:320-340`. **W3 must falsify or confirm that.** |
| `MAINLINE_WEB_ROOT` | `var.web_root` | `/var/task/web` |
| `LOG_LEVEL` | `var.log_level` | also drives `logging_config.application_log_level` |
| `MAINLINE_DEMO_ALLOW_MUTATION` | **not set** | guard is armed |
| `MAINLINE_MAX_RESPONSE_BYTES` | **not set** | `static_site.max_response_bytes()` default applies |
| `MAINLINE_DEBUG` | **not set** | tracebacks suppressed in 500 bodies |

`infra/envs/demo/variables.tf` declares **no** `scenario_permit_id`, so the module default
is what ships. Confirm with `terraform plan` output, not by reading.

### 3.2 Databases on the LOCAL node (measured today)

`SHOW DATABASES` on `postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable`:

| Database | `mainline.permit` | `trappoint.deploy_chain` | `trappoint.schema_migration` | Use it for |
|---|---|---|---|---|
| **`d_demolead`** | 1 row, `dec0de00-0006-…`, `dispositioned/1/2/1` | marker `271/271/0` | 0 | **built by me today with `cloud_chain.py --recreate` + `seed_demo.py`. The closest local thing to Cloud `mainline_demo`.** Read freely. **Do not mutate it** — other analysts share it. |
| `w_w7` | same demo permit | marker present | 0 | second Cloud-shaped copy (another wave's; **read-only, never write**) |
| `w_w6` | 0 permits | **absent** | **325** | a `trappoint migrate up` database — the *other* ledger. W4's control case |
| `w_w5_bare` | `mainline.permit` does not exist | absent | absent | the `no_bookkeeping` 503 case |
| `w_w4_api_transitions` | 31 permits, mixed states | absent | 0 | non-demo subjects — the only place a mutating POST is legal |
| `w_w1_demo`, `w3_demo_api_*`, `w_w1` | demo permit present | absent | 0 | seeded but marker-less |

**If you need to WRITE, build your own:**

```bash
PY="D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe"
cd /d/CoackroachDBxAWS/mainline
"$PY" scripts/deploy/cloud_chain.py --dsn "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable" \
      --database d_<your_id> --recreate --out "<YOUR SCRATCHPAD>/chain.json"      # ~2 min, 271 files
"$PY" scripts/deploy/seed_demo.py  --dsn "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable" \
      --database d_<your_id>            --out "<YOUR SCRATCHPAD>/seed.json"       # ~0.4 s
```

`--out` **must** point into your scratchpad. Writing into `evidence/` is a repo mutation.
`seed_demo.py` prints `VERDICT  SEEDED AND REFUSABLE` when it worked.

### 3.3 The harness — how to invoke the REAL handler

There is no web framework. `handler(event, context)` **is** the server. Write this to your
scratchpad and import it; do not shell out to a server.

```python
import json, os, sys
DB = "d_demolead"                              # or your own d_<id>
os.environ["MAINLINE_DSN"] = f"postgresql://root@127.0.0.1:26257/{DB}?sslmode=disable&connect_timeout=8"
os.environ["MAINLINE_DEMO_PERMIT_ID"] = "dec0de00-0006-4000-8000-000000000001"
os.environ["MAINLINE_WEB_ROOT"] = r"D:/CoackroachDBxAWS/mainline/verticals/mainline/apps/console/dist"  # W5 only
sys.path.insert(0, r"D:/CoackroachDBxAWS/mainline/verticals/mainline/apps/demo-api/src")
from mainline_demo_api import app

def ev(method, path, body=None, qs=None, stage="$default", headers=None):
    return {"version": "2.0", "rawPath": path, "rawQueryString": "",
            "queryStringParameters": qs, "headers": headers or {},
            "body": json.dumps(body) if body is not None else None,
            "isBase64Encoded": False,
            "requestContext": {"stage": stage, "http": {"method": method, "path": path}}}

r = app.handler(ev("GET", "/v1/health"))
print(r["statusCode"], r["body"][:400])
```

Note: setting `MAINLINE_DSN` is a **deviation from the deployment**, which uses
`MAINLINE_DSN_PARAM` + SSM. W6 owns the SSM path specifically; everyone else may use
`MAINLINE_DSN` but must say so.

The seeded identifiers (`scripts/deploy/seed_demo.py:104-110`, and the seed files):

```
permit  dec0de00-0006-4000-8000-000000000001    check   dec0de00-0007-4000-8000-000000000001
site    dec0de00-0001-4000-8000-000000000001    receipt dec0de00-0008-4000-8000-000000000001
clause  dec0de00-0004-4000-8000-000000000001    run     dec0de00-0009-4000-8000-000000000001
event   dec0de00-0005-4000-8000-000000000001    head commit 9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39
```

`mainline_demo_api.scenario.EXPECTED` (`scenario.py:120-129`) holds a **completely different**
set — the uuid5 derivation (`permit 077a6fdd-2167-559c-b2ff-8e3c8352504d`). That table is the
in-code fallback for a database nobody configured. **Anywhere a module uses a `scenario.*`
derived id against the `dec0de00` seed is a candidate defect of exactly the shape this wave
hunts.** Every analyst should watch for it inside their own slice.

---

## 4 · EARLY FINDINGS FROM SCOPING (measured, not assumed)

These are **starting points, not conclusions.** The owning analyst confirms, quantifies, and
severity-rates each. `HEAD = 2dc5c86` at the time of measurement.

### 4.1 The sealed evidence bundle and the live API disagree on the demo's headline POST — owner **W5**, cross-check **W10**

`verticals/mainline/apps/console/fixtures/bundles/demo-cloud/manifest.json` (captured
`2026-08-10T04:04:53Z`, before the write-protection guard existed) contains a frame
`frames/POST-1fc00b9fc7eccb33.json` keyed
`POST /v1/permits/dec0de00-0006-4000-8000-000000000001/merge` whose recorded
`response.status` is **409**, body an `invoke` envelope with a refusal.

The live handler today answers **423 `demo_subject_write_protected`** with a *non-envelope*
error object (measured, §4.4). A judge who replays the bundle and then curls the same path
sees two different answers to the same request, and the bundle is the one labelled sealed.
Determine: is this frame served at `/bundle/…` from the deployed origin, does the console
replay it, and does anything reconcile the two.

### 4.2 `verticals/mainline/apps/console/dist` is STALE relative to `src` — owner **W10**

Four source files are newer than `dist/index.html` (built 2026-08-10 21:04):

```
src/app/composition.tsx
src/app/source-select.ts
src/features/gate/demo-driver.module.css
src/features/gate/DemoDriver.tsx
```

`build_lambda.sh:22` packages `verticals/mainline/apps/console/dist/` as `web/`. If the build
is not re-run, **the deployed console is not the console in this repository** — and
`DemoDriver.tsx` is one of the four. Both `src` and `dist` still carry the string
`POST /v1/demo/gate-run is not addressable from this console`
(`DemoDriver.tsx:255`; `dist/assets/DemoDriver-BtgTQ3x7.js`), so the panel that a judge will
click first may still print that the demo's own endpoint cannot be reached — even though
`app._routes()` declares it and it answers 200. Determine what the built bundle actually
renders and under what condition.

### 4.3 The gate run is genuinely PROVEN on a real `demo_world.sql` seed — confirmed, owner **W2**

Against `d_demolead`, freshly built and seeded today, through `app.handler`:

```
POST /v1/demo/gate-run -> 200   verdict: PROVEN
  beat 1 read                    outcome=read      sqlstate=00000                                        matched=True
  beat 2 merge                   outcome=refused   sqlstate=23514  constraint=gate_closed_when_issued    matched=True
  beat 3 projection_drift_attack outcome=refused   sqlstate=P0001  constraint=mainline.fn_permit_merge_gate matched=True
  beat 4 admit                   outcome=admitted  sqlstate=00000                                        matched=True
```

The beat-4 signer-FK defect is **closed** by the concurrent wave's
`mainline_demo_api/credentials.py` (untracked, in flight). W2 confirms it holds and pins
exactly which rows beat 4 needs.

### 4.4 The four kernel POSTs, anonymous, through the real handler — confirmed, owner **W3**

Against `d_demolead` (fresh seed, `MAINLINE_DEMO_ALLOW_MUTATION` unset):

```
POST /v1/permits/dec0de00-0006-…/merge              -> 423 demo_subject_write_protected
POST /v1/permits/dec0de00-0006-…/checks:materialise -> 423 demo_subject_write_protected
POST /v1/permits/dec0de00-0006-…/suspend            -> 423 demo_subject_write_protected
POST /v1/checks/dec0de00-0007-…/disposition  {}     -> 422 unprocessable_request ("body member 'rationale' is required")
POST /v1/checks/dec0de00-0007-…/disposition  <valid body> -> 423 demo_subject_write_protected
```

State before and after the valid-body call was identical
(`('dispositioned',1,2,1)`, 0 dispositions, 0 merge_records) — **nothing was written.** The
lane holds. Two live questions for W3: (a) `sign_disposition` validates the body *before*
the guard (`transitions.py:915-941`), so the 4th endpoint's refusal is order-dependent — is
there any body that reaches a write before the guard; (b) `transitions.py:971,973` still
derives `_sha("cred","signer")` / `_sha("cred","cosigner")` — the **same** derivation that
was the beat-4 defect — in the sibling path that `credentials.py` did *not* touch.

### 4.5 `GET /v1/change-requests/{id}` returns 404 on the seeded world — owner **W1**

```
GET /v1/change-requests/dec0de00-000a-4000-8000-000000000001 -> 404
{"error":{"kind":"notfound","detail":"no mainline.change_request row with cr_id …", …}}
```

`demo_world.sql` / `demo_permit.sql` seed no `mainline.change_request`. Whether that is a
declared STAGED hole (`verticals/mainline/demo/DEMO-HONESTY.md`) or a panel that 404s in front
of a judge is W1's to settle, with the console's rendering of it W10's.

### 4.6 `GET /v1/health` is honest and complete on a Cloud-shaped database — owner **W4**

```
GET /v1/health -> 200
{"applied_by":"scripts/deploy/cloud_chain.py","database":"w_w7","deploy_chain_applied":271,
 "deploy_chain_files":271,"migrations_applied":0,
 "schema_fingerprint":"8cb8a7244a2750dedd8cfd35ba7adb686be981fd5cbba4ea09e29895304a5f03",
 "cluster_version":"CockroachDB CCL v26.2.5 …","ok":true,"seconds":0.0208}
```

`migrations_applied: 0` is a **true** count of `trappoint.schema_migration`; the applier that
built this database writes `trappoint.deploy_chain` instead. Two appliers, two ledgers. Note
that the bundle's `manifest.json` records a *different* hash —
`schema_version: "chain 271/271 applied, 0 failed; tree_fingerprint fe27b6208d2281929a9d3c554e4612ac…"`
— a **tree** fingerprint, not the attestation fingerprint `/v1/health` reports. W4 determines
whether anything (console chrome, judge pack, README) invites a comparison between two numbers
that were never the same quantity.

### 4.7 `conn.autocommit` stays `False` after any transition, for the life of the container — owner **W6**

Measured: after `POST /v1/demo/gate-run`, `db.connection().autocommit` is `False` and stays
`False` across a subsequent `GET /v1/permits/{id}` (which still answered 200) and across
three further POSTs. `db._open` opens with `autocommit=True`; `transitions._prepare`
(`transitions.py:293-294`) and `_demo_gate_run` (`transitions.py:1032-1033`) flip it and never
restore it. W6 must determine what this costs on a **warm Lambda container against Cloud** —
specifically whether `health()`'s `42P01` fallback, `db._alive`, or `reads.read_transaction`
can inherit an open transaction, and whether that is how a demo starts answering `40001` to
requests that conflicted with nothing.

---

## 5 · THE TEN ANALYSTS

Slices are **disjoint by subject matter**. Where two touch the same file they touch different
questions; the boundary is stated in each brief. Each analyst writes **exactly one** file.

| # | Analyst | Output file (the only file you may write) |
|---|---|---|
| W1 | Route matrix — all 17 routes against the real seed | `docs/diagnosis/demo-routes-matrix.md` |
| W2 | Gate-run beats: exact SQL, exact rows required | `docs/diagnosis/demo-gate-run-beats.md` |
| W3 | Write-protection lane and the transition surface | `docs/diagnosis/demo-write-protection.md` |
| W4 | `/v1/health`, the two ledgers, and what its numbers mean | `docs/diagnosis/demo-health-endpoint.md` |
| W5 | Static site and the sealed evidence bundle | `docs/diagnosis/demo-static-bundle.md` |
| W6 | Cold start, DSN/SSM, connection lifecycle, published env | `docs/diagnosis/demo-cold-start-env.md` |
| W7 | Concurrency, 40001 retries, repeat / out-of-order / stale | `docs/diagnosis/demo-concurrency-retries.md` |
| W8 | Error paths — every non-2xx a judge can provoke | `docs/diagnosis/demo-error-paths.md` |
| W9 | Leakage and embarrassment sweep over every emitted byte | `docs/diagnosis/demo-leakage-sweep.md` |
| W10 | The console as a judge experiences it, in a browser | `docs/diagnosis/demo-console-ux.md` |

### Boundaries, stated once so nobody duplicates

* **W1 owns status codes and envelope shape per route. W8 owns the error paths that require
  *inducing* a fault** (no DSN, dead database, oversized response, broken body, 501 branch).
  If you can reach it by asking for a normal resource, it is W1's; if you have to break
  something to see it, it is W8's.
* **W2 owns the gate-run's four beats. W3 owns the four console kernel POSTs and the guard.**
  Both read `transitions.py`; W2 stops at `_demo_gate_run`, W3 stops at everything else.
* **W5 owns bytes served from `web/` and the bundle's internal integrity. W10 owns what the
  browser does with them.**
* **W6 owns the environment and the container. W7 owns what two containers do at once.**
* **W9 reads everything and owns nothing exclusively** — its slice is a property (leakage), not
  a file set. Where W9 finds a leak inside another analyst's artefact, W9 reports it and names
  the other analyst.

---

## 6 · THE BRIEFS

Each brief is self-contained. All ten begin from §0, §3.2 and §3.3 above.

### W1 — Route matrix: all 17 routes, against the seed the deployment actually uses
**File: `docs/diagnosis/demo-routes-matrix.md`**

Enumerate `app._routes()` (`app.py:151-206`) and prove, by **running the handler**, what each
of the seventeen answers. Build a matrix: route × {seeded id, a well-formed id that is not
seeded, a malformed id, a 129-char id, an id containing `/` or `%2F`, absent id} × {declared
method, a wrong method, `OPTIONS`, `HEAD`}. For every 200, validate the body against the
contract in `verticals/mainline/apps/console/contracts/*.schema.json` named by
`envelope.SCHEMA_IDS`, and report every field the contract requires that the response omits
or the response carries that the contract forbids. Cover the query parameters each read
accepts (`reads.py` is 2,348 lines — find them; `as_of`, `site_code` and `limit` appear in the
bundle's captured keys) including absent, empty, malformed, and out-of-range values. Confirm
the `Route` regex `[A-Za-z0-9._~-]{1,128}` behaves as `app.py:135-146` claims for a path
parameter that could address a different resource. Confirm the 405 branch names the right
methods and the 404 branch lists `declared`. Establish which routes have **no seeded subject
at all** — I measured `change_request` → 404 (§4.5); find the rest, and for each say whether
`verticals/mainline/demo/DEMO-HONESTY.md` declares it. Also settle
`GET /v1/clauses/{uuid}/versions/{commit}`: with `commit_id=1` it answers 400 *"a half byte is
not a byte"*; find what the console actually sends and whether the seeded head commit
`9f12114d…` (64 hex chars) round-trips. Do **not** induce transport faults — that is W8. Do
**not** analyse the four kernel POSTs' semantics — that is W3; you only pin their status codes
and that a POST to a real path never 404s. Report each finding with the exact `file:line` on
each side, the command, the real output, the judge-visible failure, and a severity.
**Done when:** every one of the 17 routes has a measured row for at least the seeded-id and
one-negative case, every 200 is contract-checked, and every non-200 on a *normal* request is
explained by a cited line.

### W2 — The gate run: every beat, its exact SQL, and the exact rows it needs to exist
**File: `docs/diagnosis/demo-gate-run-beats.md`**

`gate_run.py` (745 lines) plays four beats in one `SERIALIZABLE` transaction that is rolled
back. For **each beat in order**, extract the literal SQL it executes (`_MERGE_SQL`,
`_FORCE_SQL`, `_DISPOSITION_SQL`, `_MERGE_RECORD_SQL`, `_FINGERPRINT_SQL`, `_PERMIT_ROW_SQL`
and everything `scenario.resolve` runs), and for each statement enumerate **every row it
requires to exist** — every foreign key target, every CHECK, every trigger
(`fn_disposition_project`, `fn_permit_merge_gate`, `check_materialised`) and every lattice or
vocabulary row. Then prove, row by row against `demo_world.sql` and `demo_permit.sql`
(read-only `SELECT`s against `d_demolead`), that each required row is seeded, and name any
that is not. This is the exact defect class that produced the beat-4 signer FK: `gate_run`
derived `sha256("cred"+"signer") = 487adc50…` while the seed carries
`digest('mainline-demo/credential/demo.signer') = ff356d14…`. The concurrent wave added
`mainline_demo_api/credentials.py` and modified `gate_run.py`; **both are in flight** — pin
what the current text does, record `git rev-parse HEAD` and `git status` for those two paths,
and state clearly if they change under you. I measured `verdict: PROVEN` with all four beats
`matched_expectation=True` on a fresh seed today (§4.3) — confirm it, then go past it: check
`persisted`, `persistence_check`, `transaction` (the logical-timestamp witness that the beats
shared one transaction), `failures`, `run_id`, and `schema_id` against
`demo-api/contracts/gate-run.schema.json`. Verify the claim in `gate_run.py:45-62` that each
write beat is fenced by `SAVEPOINT`/`ROLLBACK TO SAVEPOINT` and that a refusal undoes only its
own beat. Verify that `verdict` can be anything other than `PROVEN` — construct a database
where a beat does not match and show the run says so, because a demo that always reports
success is not evidence. Do **not** analyse the guard or the four kernel POSTs (W3), and do
**not** analyse concurrent/repeat invocation (W7).
**Done when:** every beat has its SQL, its complete required-row list, a measured
present/absent verdict per row, and the run's non-beat fields are contract-checked; plus at
least one constructed non-`PROVEN` run.

### W3 — The write-protection lane and the rest of the transition surface
**File: `docs/diagnosis/demo-write-protection.md`**

`transitions.py` is 1,148 lines and owns the four console kernel POSTs. Prove the guard
(`_demo_guard`, `transitions.py:342-402`) for **each** of the four, on **each** of these
databases: `d_<your own>` seeded (guard should refuse), a database where the demo permit is
absent (`demo_subject_unidentified` — the step-3 branch), and `w_w4_api_transitions` where 31
non-demo permits exist and the write is legal. For each, record state before and after and
show that nothing was written when it refused. Then attack the ordering: `_sign_disposition`
(`transitions.py:894-941`) validates `kind`, `defeater_code`, `rationale`, `signer_sub` and
`countersigner_sub` **before** it calls `_demo_guard`, so the demo check answers 422 to an
empty body and 423 to a valid one (measured, §4.4). Find whether any input reaches a write, a
lock, or a side effect before the guard runs — including `_prepare(conn)` at line 931, which
flips `autocommit` on the shared connection *before* the guard has decided anything. Second
target: `transitions.py:971` and `:973` still compute `_sha("cred","signer")` and
`_sha("cred","cosigner")` — the identical derivation that was the beat-4 defect, in the path
`credentials.py` did not touch. Determine, by executing it against a legal non-demo subject on
`w_w4_api_transitions`, whether that path raises a foreign-key violation, and whether the
resulting error is dressed up as a gate refusal (`_refused`) — a constraint violation reported
as though the gate had spoken is the worst possible failure for this product. Third target:
`MAINLINE_DEMO_SITE_ID` is deliberately not published, so `scenario.site_id` falls back to
`c333eb17-a6c8-5729-8e73-8d49a7ab3971` while the seeded site is
`dec0de00-0001-4000-8000-000000000001`; `infra/modules/demo-api/variables.tf:320-340` argues
it is inert because `fn_disposition_project` projects the site away. **Falsify or confirm that
by running it**, not by reading the argument. Do not analyse the gate-run's four beats (W2).
**Done when:** every one of the four POSTs has a measured guard verdict on all three database
shapes with before/after state, the ordering question is settled by execution, and the
`_sha("cred",…)` and `SITE_ID` questions each have a run behind their answer.

### W4 — `/v1/health`: the two ledgers, and what its numbers mean to a judge
**File: `docs/diagnosis/demo-health-endpoint.md`**

`health.py` is 331 lines of argument about two appliers and two ledgers. Run
`GET /v1/health` through `app.handler` against **five** database shapes and record the full
body for each: `d_demolead` / `w_w7` (marker present, `schema_migration` = 0 — I measured
`deploy_chain_applied: 271`, `migrations_applied: 0`, `ok: true`, §4.6); `w_w6` (325 rows in
`schema_migration`, **no** `deploy_chain`); `w_w5_bare` (no `mainline`, no bookkeeping);
`MAINLINE_DSN` unset and `MAINLINE_DSN_PARAM` unset (the `dsn_unset` 503); and a DSN pointing
at a port nothing listens on (the `unreachable` 503). Prove the `42P01` two-statement fallback
described at `health.py:96-116` actually fires and that the second statement is the one
without the marker subqueries — and prove the claim that a missing marker is *structurally
incapable* of producing a 503. Prove `db._open`'s `autocommit=True` really does leave no
transaction after the failed first statement (`SELECT 1` immediately after). Then the judge's
question: `migrations_applied: 0` is a TRUE count of `trappoint.schema_migration` and reads to
a stranger as *no migrations ran*. Determine every place that number is displayed or quoted —
the console's honesty chrome, `verticals/mainline/demo/judge/**`, `README.md`, `VERIFY.md`,
the GitHub Actions health cron — and whether any of them shows it without `applied_by` and
`deploy_chain_applied` beside it. Separately: `/v1/health` reports
`schema_fingerprint 8cb8a724…` (a `trappoint.schema_attestation` value) while the sealed
bundle's `manifest.json` records `tree_fingerprint fe27b620…`. Establish whether any artefact
invites a reader to compare those two, and what a judge concludes if they do. Do not analyse
static bytes (W5) or cold-start/DSN resolution mechanics (W6) — you consume the DSN, you do
not audit how it is fetched.
**Done when:** five measured bodies, the 42P01 fallback demonstrated, and a complete list of
every surface that displays `migrations_applied` with a verdict on each.

### W5 — The static site and the sealed evidence bundle
**File: `docs/diagnosis/demo-static-bundle.md`**

Under DECISION D1 one Lambda Function URL serves both `/v1/*` and everything else
(`static_site.py`, 611 lines). Reproduce the deployed tree: `web/` = `console/dist/` plus
`web/bundle/` = `console/fixtures/bundles/demo-cloud/` (`build_lambda.sh:22-23`). Serve it via
`app.handler` with `MAINLINE_WEB_ROOT` pointed at a staged copy **in your scratchpad** (do not
build into the repo). Then: walk every path the site references — parse `dist/index.html`,
follow every `<script>`/`<link>`/asset URL, and prove each resolves to a 200 with the right
`content-type` and `cache-control` (`static_site._cache_control`). Attack `resolve()`
(`static_site.py:325`) with `..`, `%2e%2e`, absolute paths, backslashes, null bytes,
double slashes, a very long path, and a path that escapes the root — a traversal on an
unauthenticated origin is critical. Verify the SPA fallback: which paths return `index.html`
and which return 404, and confirm `/v1/*` can never reach the static branch
(`static_site.is_api_path`). Verify the `.gz` sibling logic and that a client without
`accept-encoding: gzip` still gets a correct body. Verify `max_response_bytes()` and the 413
refusal, including `app._too_large`'s claim that a refusal can never itself be refused — set
`MAINLINE_MAX_RESPONSE_BYTES` below the refusal's own length and show what happens. Then the
bundle: `manifest.json` names 24 files with `sha256` and `bytes` — **recompute every one** and
report any mismatch or missing file, and confirm `frames/` and `sql/` hold nothing the
manifest does not name. Settle §4.1: the frame
`POST /v1/permits/dec0de00-0006-…/merge` records `response.status: 409` with an `invoke`
envelope, while the live endpoint answers 423 with a non-envelope error. Establish whether
that frame is reachable from the deployed origin and what reconciles the two. Also check
whether source maps ship (`dist/assets/*.js.map`, 18 files, ~2.5 MB — `build_lambda.sh:117`
says they are stripped by default; prove which way the build actually goes). Do not analyse
browser behaviour (W10) or scan for leaked strings (W9) — you own bytes and integrity, they
own rendering and secrets.
**Done when:** every referenced asset is resolved, traversal is attacked with real inputs, all
24 manifest digests are recomputed, and the 409/423 bundle-vs-live divergence has a verdict.

### W6 — Cold start, DSN resolution, connection lifecycle, and the published environment
**File: `docs/diagnosis/demo-cold-start-env.md`**

A judge's first click hits a **cold** container. Measure import cost: time
`import mainline_demo_api.app` from a clean interpreter, and identify everything imported at
module scope (`scenario._selfcheck()` runs at import — `scenario.py:131-145`; what else?).
Audit `db.resolve_dsn` (`db.py:258-300`): the deployment sets `MAINLINE_DSN_PARAM`, **not**
`MAINLINE_DSN`, so the first invocation makes a hand-rolled SigV4 call to SSM
(`db.py:152-256`) using `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`
from the runtime. Determine what happens on every failure of that path — no credentials,
expired token, wrong region (`AWS_REGION` vs `AWS_DEFAULT_REGION`), parameter not found,
`AccessDenied`, a timeout — and what status and body a judge sees for each; note that a
SigV4 implementation this project wrote itself has never run in a Lambda in this repo's
evidence. **Do not call AWS to mutate anything; read-only probes only, and never print a
credential or a DSN.** Verify `db.redact` is applied everywhere a DSN could reach a log or a
body. Then the container: `db.connection()` caches for the container's life; `db._alive`
decides reuse; `db.close()` is called on some error paths and not others — map which. Own
§4.7: `transitions._prepare` (`:293`) and `_demo_gate_run` (`:1032`) set
`conn.autocommit = False` and never restore it, and I measured it staying `False` across
subsequent reads and POSTs in one process. Determine the real cost against a cluster that
actually enforces serializable isolation: can a later request inherit an open transaction,
does `reads.read_transaction` or `health()` misbehave, and is this how the demo starts
answering `40001` to requests that conflicted with nothing. Finally, cross-check §3.1: for
**every** environment variable Terraform publishes, name the `file:line` that reads it and
prove the handler behaves as the variable's documentation claims — and name every variable
the code reads that Terraform does **not** publish. Do not analyse concurrency between two
containers (W7).
**Done when:** cold import is timed, every SSM failure mode has a measured or explicitly
reasoned status, the autocommit leak has a demonstrated consequence or a demonstrated
harmlessness, and the env-var table is complete in both directions.

### W7 — Concurrency, 40001 retries, and repeat / out-of-order / stale invocation
**File: `docs/diagnosis/demo-concurrency-retries.md`**

Cloud `mainline_demo` is a Basic serverless cluster that returns `40001` under contention; a
single-node local Docker node effectively never does, which is why nothing in the test suite
has seen it. First, inventory: for every statement path the demo can reach — `gate_run`'s four
beats, each of `transitions`' five entry points, `reads.read_resource`, `health()` — say
whether a `40001` retry loop exists, citing the `file:line` of the loop or of its absence.
`scripts/deploy/cloud_chain.py` and `seed_demo.py` **do** have one (`Applier`, `MAX_ATTEMPTS`,
`RETRYABLE`) and both accept `--inject-40001 N`; the request path is the question.
`gate_run._record_refusal` raises `_Undecided` on `40001` (`gate_run.py:353-390`) — follow it
and report exactly what a judge sees when a beat comes back undecided. Second, **produce real
contention locally**: run two or more concurrent `POST /v1/demo/gate-run` invocations against
the same seeded database from separate processes, and separately hold a conflicting
transaction open from a second connection while a gate-run executes; record every SQLSTATE and
every response body. `d_demolead` is shared — build your own `d_<id>` for anything that
writes. Third, the judge who clicks in an order nobody designed for: invoke gate-run twice
back to back (I measured two consecutive 200s), invoke it while a kernel POST is in flight,
invoke a beat's endpoint with a **stale** `expected_gate_epoch` (the bundle's captured merge
body carries `"expected_gate_epoch": 1`), point `MAINLINE_DEMO_PERMIT_ID` at a permit that
exists but is in the wrong state (`w_w4_api_transitions` has `draft`, `checks_materialised`,
`merged` and `suspended` permits — use them), and at a permit that does not exist. Report what
each answers and whether the answer is honest. Do not audit the guard's *policy* (W3) or the
beats' *SQL* (W2) — you own what happens when they run at the same time or in the wrong order.
**Done when:** the retry-loop inventory is complete with citations, real contention has been
produced and its responses recorded, and each of the repeat/stale/out-of-order cases has a
measured answer.

### W8 — Error paths: every non-2xx a judge can provoke, and what they see
**File: `docs/diagnosis/demo-error-paths.md`**

`app.py:44-58` declares the status contract: 200, 400, 404, 405, 409, 413, 501, 503, 500.
**Induce every one of them** through `app.handler` and record the exact body. Specifically:
503 `dsn_unset` (both DSN variables unset); 503 `database_unreachable` (DSN to a dead port, to
a wrong database name, to a host that black-holes); 500 `database_error` (a read whose
statement raises — find one, e.g. by pointing at `w_w5_bare` or `w_w3`, which I measured
lacks `permit.open_blocking`); 500 `internal_error` (a non-`psycopg` exception inside a read);
501 `not_implemented` (both branches — module absent, and module present without
`handle_transition`; simulate by import shadowing in your own process, never by editing the
repo); 400 `malformed_body` (invalid JSON, invalid base64 with `isBase64Encoded`, a body that
is a JSON scalar rather than an object); 413 (drive a response over
`MAINLINE_MAX_RESPONSE_BYTES`); 405 and 404 with their `allow`/`declared` payloads. For each,
answer three questions: (a) does the body leak anything a public demo should not emit —
SQLSTATE detail is deliberate, a stack trace is not; `MAINLINE_DEBUG` gates `traceback` at
`app.py:~330`, confirm it is off and confirm the gate works; (b) does
`console/src/data/transport.ts` classify it the way `app.py:32-42` claims — a non-2xx with no
parseable envelope becomes a `status` transport failure and the body is shown to the judge
verbatim, so **every error body is judge-visible text**; (c) is the wording something you would
be happy to see on a projector. Also prove the handler's central claim: **it never raises.**
Fuzz the event shape — missing `requestContext`, `rawPath` absent, payload format 1.0
(`httpMethod`/`path`), a real stage prefix, `event=None`, `headers=None`, a body that is
already a dict, unicode paths, a 129-character path parameter — and report any input that
produces an exception instead of a JSON body. Do not re-report normal-request statuses (W1).
**Done when:** each declared status has an induced example with its real body, the
never-raises claim has been fuzzed, and each body has a verdict on leakage and on wording.

### W9 — Leakage and embarrassment sweep over every byte this origin can emit
**File: `docs/diagnosis/demo-leakage-sweep.md`**

The URL is `authorization_type = NONE`. Everything the function can emit is public. Sweep
**all** of it: every `web/**` byte (including `dist/assets/*.js` and any `*.js.map` that
ships), every file in the sealed bundle (`manifest.json`, 18 `frames/*.json`, 5 `sql/*.txt` —
note the `sql/` files are verbatim SQL transcripts and are the highest-risk artefacts here),
every API response body from a normal request and from each induced error, and every log line
the handler writes at the configured `LOG_LEVEL`. Search for: absolute developer paths
(`D:/CoackroachDBxAWS`, `D:\\`, `/home/`, `/Users/`), the founder's username (`shaug`,
`Shaugato`, the git author email), AWS account ids (12-digit runs — **note the known
false-positive `322122547200`, which is 300 GiB in bytes, and do not report it**), ARNs,
hostnames and Function URL ids, SSM parameter names and paths, DSNs or anything resembling one
even redacted, private hostnames, internal ticket or worker ids, `TODO`/`FIXME`/`XXX`/`HACK`
left in shipped text, profanity or informal commentary, and any stack trace or Python
traceback. I already checked the bundle's `manifest.json` and found none of `shaug`, `D:/`,
`amazonaws`, `lambda-url` or `077a6fdd` — extend that to every file. Second half of your slice:
**claims the demo contradicts.** Read `README.md`, `VERIFY.md`, `verticals/mainline/demo/DEMO-HONESTY.md`,
`verticals/mainline/demo/judge/**` and `docs/leads/ship-final.md`, extract every checkable
assertion about what the demo does, and verify each against the behaviour this wave is
measuring — a public claim the live demo falsifies is exactly what a judge will find. Where a
leak lives inside another analyst's artefact, report it and name that analyst rather than
editing anything. **Never print a real credential into your file — describe its location and
shape.**
**Done when:** every emittable byte-source has been swept with a named command, every hit is
either a finding or an explained false positive, and every checkable public claim has a
verdict.

### W10 — The console as a judge actually experiences it, in a browser
**File: `docs/diagnosis/demo-console-ux.md`**

Serve the staged `web/` tree over `http://127.0.0.1:<port>` — `scripts/deploy/local_furl.py`
exists for exactly this; read it first and use it if it fits, otherwise a plain static server
plus the handler. Load the console **in a real browser** and drive it as a judge would: click
every panel, in a sensible order and then in a deliberately stupid one. Record the **browser
console** (errors, warnings, failed fetches, CSP violations, source-map 404s) and the network
log for every request the SPA makes, and confirm every one of them corresponds to a route in
`app._routes()`. Settle §4.2: four `src` files are newer than `dist/index.html`, including
`DemoDriver.tsx` and `composition.tsx`, so **the built console may not be the console in this
repo**. Determine what the built bundle actually renders for the demo driver, and in
particular whether a judge sees
*"POST /v1/demo/gate-run is not addressable from this console"* (`DemoDriver.tsx:255`,
present in `dist/assets/DemoDriver-BtgTQ3x7.js`) on the panel that is the whole demo — the
router declares the route and it answers 200, so a banner saying otherwise is a self-inflicted
NO-GO. Check `console/src/data/resources.ts` (sixteen `declare()` calls) against the router's
seventeen and `console/src/data/contracts.ts` against `envelope.SCHEMA_IDS`; confirm
`tests/test_routes_gate_run.py` still pins the difference to exactly one endpoint. Check what
the UI renders when a read 404s — `change_requests` returns 404 on the seeded world (§4.5) —
and whether that looks like a broken demo or a declared gap. Check the honesty chrome:
STAGED badges, the verification seal, the health numbers, and whether the bundle-replay source
selector (`src/app/source-select.ts`, also newer than `dist`) can put live and replayed
answers side by side — where §4.1's 409-vs-423 divergence would become visible on screen.
Check mobile width and a dark colour scheme if the console supports one. Do not audit static
bytes or bundle digests (W5).
**Done when:** every panel has been clicked with the browser console captured, the
stale-`dist` question is settled by inspecting the built artefact's behaviour, and each
judge-visible defect has a screenshot-or-transcript, a `file:line`, and a severity.

---

## 7 · REPORTING FORMAT (all ten)

Each file: a one-paragraph verdict at the top, then findings ordered **most severe first**,
then a "what I could not run and why" section, then a reproduction appendix.

Each finding:

```
### F-<Wn>-<k> · <one-line claim>
Severity: CRITICAL | HIGH | MEDIUM | LOW | COSMETIC
Divergence: <path:line>  ←→  <path:line>          (the exact line on EACH side)
Command:    <what you ran, verbatim>
Output:     <what it really printed, verbatim, trimmed but not paraphrased>
Judge sees: <the failure a user or judge would actually experience>
Confidence: MEASURED | REASONED, NOT RUN  (+ why, if the latter)
```

Rank honestly. A cosmetic mismatch reported as CRITICAL costs the next wave more than it
saves. `HEAD` at the time of your run belongs in every file's header, because the repository
is moving while you read it.
