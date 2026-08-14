<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PROVEN-STATE — what is true right now, and the command that shows it

This file exists so that **after the current wave lands, any regression is a named,
checkable difference rather than something nobody noticed.** It is not a summary of what
we believe. Every number below was produced by running the command beside it, on
2026-08-14/15, and the real output is quoted.

**Read this first:**

* Where a row says **BOUND**, the number **may never move**. If it moves, that is a
  regression, full stop.
* Where a row says **MEASUREMENT**, the number describes *a particular build or a live
  system*. It legitimately moves on a rebuild or a reseed. **Do not file a moved
  MEASUREMENT as a regression** — check the property beside it instead.
* Where a row says **NOT REPRODUCED**, the recorded baseline did **not** come back on this
  machine. §11 collects all of them in one place.

---

## 0. How each number is anchored

The working tree is being edited by a large concurrent wave, so nothing here is measured
against "the worktree" without saying so.

| | |
|---|---|
| **Last-known-good commit** | `e88b8b6a7523d3100405ac1b29dfa9b337baac2c` (`e88b8b6`), *"evidence(live): the demo answers PROVEN on the public URL"* |
| **Tree state when measurement began** | `git status --porcelain` printed **0 lines** at **2026-08-14T22:31:00Z**, and `git rev-parse HEAD` == `e88b8b6`. The wave had not yet written to the tree. |
| **Clean anchor** | `git archive e88b8b6 \| tar -x -C <scratch>/e88b8b6` → **7,631 files**. Used wherever a worktree measurement could be contaminated by line-ending or in-flight edits. |
| **Measurement window** | 2026-08-14T22:31Z – 2026-08-15T00:00Z (UTC) |

Three anchoring methods are used, and each row says which:

* **[ARCHIVE]** — measured inside the clean `git archive e88b8b6` export. Immune to the wave.
* **[WORKTREE@e88b8b6]** — measured in `D:/CoackroachDBxAWS/mainline` while the tree was
  still verified clean at `e88b8b6`.
* **[LIVE]** — measured against cloud infrastructure (the Lambda, the CockroachDB Cloud
  cluster, GitHub Actions). **This can change underneath this file without any commit.**

`python` below always means `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`.
There is no `uv` and no `just` on this machine, so every command is given in plain form.

---

## 1. The gate proof — `VERDICT PROVEN` [WORKTREE@e88b8b6]

**What is true:** the whole 271-file MAINLINE migration chain applies into a throwaway
local database, and the database then refuses the merge three different ways and admits it
once a signed disposition exists. This is the central claim of the project and it
reproduces.

```
python scripts/proof/gate_refusal.py --dsn "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
```

**Exit 0.** Real output, every verdict line:

```
cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
database      w_qr_gate_refusal_proof
chain         271/271 applied, 0 failed, 146.191s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held — open_blocking 0->1 — gate_epoch 0->1 — outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
evidence      D:\CoackroachDBxAWS\mainline\evidence\gate-refusal\proof-20260814T223111Z.json
```

| Claim | Kind | Value | A regression looks like |
|---|---|---|---|
| chain applied | **BOUND** | `271/271 applied, 0 failed` | any `applied < files`, or `failed > 0` |
| `reached 0115` | **BOUND** | `True` | `False` — the gate function was never created |
| unproduced relations | **BOUND** | `(none)` | any relation named — a migration references something no file creates |
| PROJECTION | **BOUND** | `10/10 held`, `open_blocking 0->1`, `gate_epoch 0->1`, outbox `check_opened` severity **4** (client supplied 0) | `< 10/10`; a counter that does not move; severity echoing the client's 0 instead of the trigger's 4 |
| REFUSAL | **BOUND** | `REFUSED [23514] gate_closed_when_issued (reported)` | any other sqlstate, any other constraint, or `ADMITTED` |
| DRIFT | **BOUND** | `REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)` | `ADMITTED` — the out-of-band counter zeroing got through |
| ADMISSION | **BOUND** | `ADMITTED [00000]` | `REFUSED` — a legitimate merge is now blocked |
| caveats | **BOUND** | `(none)` | any caveat listed = something unproven is being tolerated |
| VERDICT | **BOUND** | `PROVEN` | anything else |
| chain wall-clock | **MEASUREMENT** | `146.191s` | **nothing.** `docs/VERIFY.md` records 55.611 s for the same chain; this box is ~2.6× slower under the concurrent wave. See §11.0 — this number is load-dependent and is *not* a defect, but it is what breaks the `--crdb=reuse` suite's fixture timeout. |

Evidence artefact written by the run: `evidence/gate-refusal/proof-20260814T223111Z.json`,
carrying `chain.files 271`, `chain.applied_count 271`, `chain.failed_count 0`,
`chain.reached_0115_fn_permit_merge_gate true`, `chain.unproduced_tables_enumerated []`,
`caveats []`, and all eight `gate_objects` true.

---

## 2. The suites

### 2.1 Collection counts — both reproduce exactly [WORKTREE@e88b8b6]

```
python -m pytest verticals/mainline/apps/demo-api/tests tests/deploy --crdb=none --collect-only -q
python -m pytest --crdb=none --collect-only -q
```

| Claim | Kind | Measured | Recorded baseline | Verdict |
|---|---|---|---|---|
| demo-api + `tests/deploy` collected | **BOUND** | **911 tests collected in 2.85s** | 911 | **MATCHES** |
| repo-wide collected | **MEASUREMENT** | **10,478 tests collected in 36.99s** | `docs/VERIFY.md` records 9,324 at an older commit | grew; suite growth is expected, a *fall* is the thing to question |

A regression: `911` moving **down** without a commit that deletes tests, or a collection
**error** (`--collect-only` exiting non-zero).

### 2.2 The `--crdb=reuse` run — **reproduces exactly, but only with the timeout raised**

```
python -m pytest verticals/mainline/apps/demo-api/tests tests/deploy \
  --crdb=reuse -q --timeout=900 --junitxml=<path>
```

Numbers read from the **`--junitxml` root element only**, never from the terminal tail:

```
<testsuite name="pytest" errors="0" failures="0" skipped="1" tests="911" time="304.795">
```

| | Recorded baseline | **Measured** | Verdict |
|---|---:|---:|---|
| collected (`tests`) | 911 | **911** | **MATCHES** |
| passed (`tests - failures - errors - skipped`) | 910 | **910** | **MATCHES** |
| `failures` | 0 | **0** | **MATCHES** |
| `errors` | 0 | **0** | **MATCHES** |
| `skipped` | 1 | **1** | **MATCHES** |
| wall clock | — | 304.795 s | MEASUREMENT |

The single skip is the recorded one, quoted from the run:

```
SKIPPED [1] verticals\mainline\apps\demo-api\tests\test_gate_run.py:1294:
jsonschema is not a workspace dependency; the structural check above is what runs
today and this turns green the day it is added
```

**The `--timeout=900` is a deviation from the committed configuration and is declared
here rather than buried.** At the committed `timeout = 120` (`pyproject.toml`), this suite
**does not complete on this machine** — it is killed twice out of two attempts. The cause
is diagnosed, is not a code regression, and is worth knowing before someone panics:

* the hang is always in the same place —
  `verticals/mainline/apps/demo-api/tests/test_row_factory_contract.py:345`, fixture
  `_w1_built`, calling `scripts/proof/gate_refusal.py:494 apply_chain(...)`;
* that fixture applies the **whole 271-file chain**, which §1 measured at **146.191 s**;
* `146 > 120`, so `pytest-timeout` (`timeout_method = "thread"`) dumps the stack and kills
  the process, and **no `--junitxml` is written at all** — which is how a run like this
  gets mistaken for "the suite is broken";
* `docs/VERIFY.md` records the same chain at **55.611 s**. This box is ~2.6× slower while a
  24-worker wave is on it. On a quiet machine 146 s falls back under 120 s and the default
  timeout is fine.

**A regression looks like:** any of the five junit numbers moving; the skip count rising
above 1, or the surviving skip being anything other than the `jsonschema` one; or a
`--crdb=reuse` failure that is *not* accompanied by a `+++ Timeout +++` stack ending in
`apply_chain`.

### 2.3 The hermetic `--crdb=none` run

```
python -m pytest verticals/mainline/apps/demo-api/tests tests/deploy --crdb=none -q --junitxml=<path>
```

```
<testsuite name="pytest" errors="0" failures="0" skipped="233" tests="911" time="52.507">
```

| | **Measured** | Kind |
|---|---:|---|
| collected | **911** | **BOUND** — identical to the `reuse` collection, as it must be |
| passed | **678** | **BOUND** |
| `failures` / `errors` | **0** / **0** | **BOUND** |
| `skipped` | **233** | **BOUND** |
| wall clock | 52.78 s | MEASUREMENT |

`678 + 233 = 911`, so nothing is unaccounted for. All 233 skips carry one named reason
(`verticals/mainline/apps/demo-api/tests/conftest.py:294`): *"the session obtained no
CockroachDB, so this cluster-backed test is skipped rather than allowed to reach a node the
session declined to obtain."*

**This lane is the honest one to run first**: it needs no cluster, no credential and no
network, it finishes in under a minute, and it cannot produce a false green because every
cluster-backed test skips with a reason instead of passing vacuously. **A regression looks
like:** a non-zero `failures`/`errors`; `678` falling; or `233` *rising*, which would mean
tests that used to run hermetically now demand a cluster.

---

## 3. The live URL, over the public internet [LIVE]

Host: `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
Measured 2026-08-14T22:34–22:35Z from this machine, over the ordinary internet, with no
credential of ours in the path.

### 3.1 `GET /`

```
curl -sS -o /dev/null -D - --compressed "$URL/"
```

```
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 2122
content-encoding: gzip
x-mainline-api: demo-static
x-mainline-static: index.html
cache-control: no-cache
vary: accept-encoding
```

| Claim | Kind | Value | Regression |
|---|---|---|---|
| status | **BOUND** | `200` | anything else; or a non-HTML body on the hostname |
| `x-mainline-api` | **BOUND** | `demo-static` | header missing = something other than our origin is answering |
| `x-mainline-static` | **BOUND** | `index.html` | a different file being served at `/` |
| `vary` | **BOUND** | contains `accept-encoding` | missing — a shared cache can now serve gzip to a client that refused it |
| `cache-control` | **BOUND** | `no-cache` | a cacheable value would let a stale console survive a redeploy |
| gzip wire bytes | **MEASUREMENT** | `2,122` | nothing — moves on any console rebuild |
| identity bytes (`accept-encoding: identity`) | **MEASUREMENT** | `4,655` | nothing — moves on any console rebuild |

### 3.2 `GET /v1/health`

```
curl -sS --compressed "$URL/v1/health"
```

```json
{"applied_by":"scripts/deploy/cloud_chain.py","cluster_version":"CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)","database":"mainline_demo","deploy_chain_applied":271,"deploy_chain_files":271,"migrations_applied":0,"ok":true,"schema_fingerprint":"ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339","seconds":0.0143,"server_date":"2026-08-14T22:34:53.217811Z"}
```

| Field | Kind | Value | Regression |
|---|---|---|---|
| `ok` | **BOUND** | `true` | `false` |
| `database` | **BOUND** | `mainline_demo` | any other database — the demo is pointed somewhere else |
| `cluster_version` | **BOUND** | `CockroachDB CCL v26.2.5 …` | a major/minor move is a cluster upgrade, not a code change; treat as an event to confirm |
| `deploy_chain_applied` / `deploy_chain_files` | **BOUND** | `271` / `271` | applied < files = the cloud chain is behind the tree |
| `migrations_applied` | **BOUND** | `0` | non-zero means the API applied migrations at runtime, which it must not |
| `schema_fingerprint` | **BOUND while the chain is 271 files** | `ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339` | **a change here with `deploy_chain_files` still 271 means the cloud schema drifted without a migration** — the single most important number in this section |
| `applied_by` | **BOUND** | `scripts/deploy/cloud_chain.py` | applied by anything else |
| `server_date` | **MEASUREMENT** | fresh | must be fresher than 900 s — a cached 200 cannot satisfy this |

### 3.3 `POST /v1/demo/gate-run`

```
curl -sS -X POST --compressed -H "content-type: application/json" -d '{}' "$URL/v1/demo/gate-run"
```

`HTTP 200`, 10,499 bytes, 2.5–2.8 s. **This call is non-mutating by construction** — the
response carries `persisted: false` and `transaction.disposition: "rolled_back"` under
`SERIALIZABLE`.

| | Kind | Value |
|---|---|---|
| `data.verdict` | **BOUND** | **`PROVEN`** |
| `data.outcome` | **BOUND** | `completed` |
| `data.failures` | **BOUND** | `[]` |
| `data.persisted` | **BOUND** | `false` |
| `data.transaction.disposition` | **BOUND** | `rolled_back` |
| `data.transaction.isolation` | **BOUND** | `SERIALIZABLE` |
| `schema_id` | **BOUND** | `https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json` |
| `data.run_id`, `elapsed_ms`, `generated_at` | **MEASUREMENT** | new every call |

All four beats, every one with `matched_expectation: true`:

| # | `name` | `outcome` | SQLSTATE | `constraint` | `constraint_source` |
|---|---|---|---|---|---|
| 1 | `read` | `read` | `00000` | — | — |
| 2 | `merge` | `refused` | **`23514`** | **`gate_closed_when_issued`** | `reported` |
| 3 | `projection_drift_attack` | `refused` | **`P0001`** | **`mainline.fn_permit_merge_gate`** | `parsed` |
| 4 | `admit` | `admitted` | `00000` | — | — |

Beat 2's refusal additionally carries `class: gate`, `diagnosis: declarative`, a
1-element **MUS** naming obligation `dec0de00-0007-…-0001` at `severity 4`,
`virulence: blood_major`, `origin: blame_ancestry`, and an **NAA** of kind
`dispose_obligations` with `cardinality 1`.

**A regression here is:** any beat's `matched_expectation` going `false`; any SQLSTATE or
constraint in the table above changing; `verdict` ceasing to be `PROVEN`; or
`persisted` becoming `true` — that last one would mean the public demo endpoint now
writes to the demo database.

---

## 4. Cloud `mainline_demo` row counts [LIVE]

Read with the DSN taken **programmatically** from `.env` and the database path segment
substituted. **The committed DSN's path segment is `defaultdb`, not `mainline_demo`** —
connecting to the DSN as written and counting rows is the trap; you will find empty or
missing tables and conclude the seed is gone. Verified: `current_database()` answered
`mainline_demo`.

Reproduce with `<scratch>/cloud_counts.py` (reads `COCKROACH_DSN`, rewrites the path,
never prints the DSN), or equivalently:

```python
p = urlsplit(dsn_from_env); dsn = urlunsplit((p.scheme, p.netloc, "/mainline_demo", p.query, p.fragment))
```

| Table | Rows | Kind |
|---|---:|---|
| `mainline.defeater_option` | **6** | seed **MEASUREMENT** |
| `mainline.permit` | **1** | seed **MEASUREMENT** |
| `mainline.blocking_check` | **2** | seed **MEASUREMENT** |
| `mainline.signing_credential` | **2** | seed **MEASUREMENT** |
| `mainline.clause` | **1** | seed **MEASUREMENT** |
| `mainline.clause_version` | **1** | seed **MEASUREMENT** |
| `mainline.ledger_leaf` | **4** | seed **MEASUREMENT** |
| `mainline.ledger_node` | **3** | seed **MEASUREMENT** |
| `mainline.ledger_checkpoint` | **3** | seed **MEASUREMENT** |
| `mainline.exposure_receipt` | **1** | seed **MEASUREMENT** |
| `mainline.disposition` | **0** | **BOUND-ish** — see below |
| `mainline.event` | **1** | seed **MEASUREMENT** |
| `trappoint.deploy_chain` | **1** | **BOUND** |

**These are seed MEASUREMENTS. The wave is expected to change the demo seed, and a
changed count is not by itself a regression.** What must survive any reseed:

* **`mainline.disposition` must be `0`.** The demo's whole point is one open obligation
  with **no** signed disposition. A non-zero count means beat 2 will stop refusing and
  `verdict` will stop being `PROVEN`. **Check §3.3 immediately if this moves.**
* **`mainline.permit` ≥ 1** and **`mainline.blocking_check` ≥ 1**, or there is nothing
  for the gate to refuse.
* **`trappoint.deploy_chain` exactly 1 row.** More than one means the chain was applied
  twice; zero means the marker was lost and `/v1/health` cannot report `deploy_chain_applied`.
  Its columns are `marker_id, tree_fingerprint, live_fingerprint, files, applied, failed,
  retried, total_seconds, applied_at, applied_by`.

The cheapest whole-seed regression check is not a row count at all — it is
`POST /v1/demo/gate-run` returning `PROVEN` (§3.3), which exercises the seed end to end.

---

## 5. `mainline_api` privileges [LIVE] — **SELECT DID NOT REPRODUCE**

```sql
SELECT privilege_type, count(*) FROM [SHOW GRANTS FOR mainline_api] GROUP BY privilege_type ORDER BY privilege_type;
```

| Privilege | Recorded | **Measured** | Verdict |
|---|---:|---:|---|
| `CONNECT` | 1 | **1** | matches |
| `USAGE` | 37 | **37** | matches |
| `SELECT` | 66 | **69** | **NOT REPRODUCED — +3** |
| `UPDATE` | 3 | **3** | matches |
| `INSERT` | 8 | **8** | matches |
| `EXECUTE` | 29 | **29** | matches |
| **total** | 144 | **147** | +3 |

Per schema (all privilege types), so a future diff can localise a move:

| schema | count | `SELECT` | `USAGE` | `INSERT` | `UPDATE` | `EXECUTE` |
|---|---:|---:|---:|---:|---:|---:|
| *(database-level)* | 1 | | | | | `CONNECT` 1 |
| `mainline` | **101** | 45 | 18 | 7 | 3 | 28 |
| `mainline_audit` | **18** | 14 | 4 | | | |
| `mainline_meas` | **10** | 6 | 4 | | | |
| `mainline_ops` | **6** | 1 | 4 | 1 | | |
| `mainline_qa` | **3** | 0 | 3 | | | |
| `public` | **3** | 0 | 3 | | | |
| `trappoint` | **5** | 3 | 1 | | | `EXECUTE` 1 |

**`mainline_qa` holds `USAGE` on the schema and `SELECT` on nothing.** That is the
documented posture (`VERIFY.md`: *"`mainline_qa` never receives an account"*) and it is
the single most important row in this table — **if `mainline_qa` ever acquires a `SELECT`,
that is a privilege regression, not a feature.**

The 69 `SELECT` grants are, in full, so the next reader can diff by name rather than by
count:

* **`mainline` (45 tables):** `blame_edge`, `blocking_check`, `boundary_certificate`,
  `cbm_account`, `change_request`, `clause`, `clause_blame_closure`, `clause_blame_current`,
  `clause_version`, `clearance_legal`, `commit_edge`, `commit_obj`, `control_failure`,
  `cosignature`, `cr_clause`, `cr_event`, `defeater_option`, `delta_witness`, `disposition`,
  `disposition_citation`, `doc`, `event`, `event_edge`, `exposure_line`, `exposure_receipt`,
  `identity_residue`, `ledger_checkpoint`, `ledger_intake`, `ledger_leaf`, `ledger_node`,
  `mechanism_predicate`, `merge_record`, `override_ledger`, `permit`, `permit_boundary`,
  `permit_clause`, `permit_event`, `permit_slice`, `person`, `receipt_expiry`,
  `refusal_ledger`, `signing_credential`, `site`, `subject_transition`, `unwitnessed_debt`
* **`mainline_audit` (14 views):** `v_agent_actions`, `v_blame_coverage`, `v_cbm_ledger`,
  `v_changefeed_health`, `v_disposition_coverage`, `v_fixity_coverage`,
  `v_gate_latency_daily`, `v_ledger_health`, `v_open_gate_summary`, `v_recall_conservation`,
  `v_silence_summary`, `v_txn_restart_daily`, `v_unused_indexes`,
  `v_weakenings_without_disposition`
* **`mainline_meas` (6):** `agent_action`, `recall_candidate`, `recall_policy`, `recall_run`,
  `silence_ledger`, `silence_receipt`
* **`mainline_ops` (1):** `outbox`
* **`trappoint` (3):** `deploy_chain`, `schema_attestation`, `schema_migration`

`VERIFY.md` §"The questions worth asking" contracts **nine** `mainline_audit` views; the
grant list carries **fourteen**, so five (`v_cbm_ledger`, `v_changefeed_health`,
`v_gate_latency_daily`, `v_txn_restart_daily`, `v_unused_indexes`) are readable but
uncontracted. That is a plausible home for the +3, but **it is not proven** — the recorded
66 was a bare count with no object list, so which three moved cannot be recovered. This
list exists so that the same question is answerable next time.

---

## 6. The ruff ratchet — **LINT 0, and the FORMAT number is mostly, but not entirely, CRLF**

```
python scripts/qa/ruff_ratchet.py
```

`ruff 0.16.1 | lint findings 656 | unformatted files 226`

| Claim | Kind | Measured | Recorded | Verdict |
|---|---|---|---|---|
| **LINT regressions** | **BOUND** | **0** | 0 | **MATCHES** |
| LINT improvements | MEASUREMENT | 1 — `E501` in `scripts/` fell `1 → 0` | — | an improvement, not a regression |
| FORMAT regressions **[WORKTREE]** | MEASUREMENT | **7 ratchet rows, 226 files** | — | see below |
| FORMAT regressions **[ARCHIVE]** | **BOUND** | **4 files** | — | **this is the real number** |

The 226 breaks down `<repo> 226` = `other/ 3`, `packages/mainline-* 5`,
`packages/trappoint-* 50`, `scripts/ 8`, `tests/ 107`, `verticals/ 53`.

**The CRLF framing is right in bulk and wrong in the tail, and the difference matters.**
Run against the clean export instead of the worktree:

```
cd <scratch>/e88b8b6 && python -m ruff format --check .
→ 4 files would be reformatted, 1550 files already formatted
```

GitHub Actions, on Linux, at this same commit, printed the **identical** line:
`4 files would be reformatted, 1550 files already formatted`. So of the 226 seen on this
Windows checkout, **222 are the CRLF artefact and 4 are real**, and the four are:

1. `docs/leads/reconcile-constants-plan.md`
2. `tests/deploy/test_furl_compression.py`
3. `verticals/mainline/apps/demo-api/tests/test_response_contract.py`
4. `verticals/mainline/apps/demo-api/tests/test_static_site.py`

**Do not dismiss the whole FORMAT red as a Windows artefact.** Those four are why
`tests/release/test_ruff_ratchet.py::test_the_ratchet_passes_on_the_real_tree` is red in
CI (§8). The regression to watch is `4` rising, or the **LINT** regression count leaving `0`.

---

## 7. The bounds that may never move [WORKTREE@e88b8b6 + package]

```
grep -n "DEFAULT_MAX_RESPONSE_BYTES" verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py
→ 279: DEFAULT_MAX_RESPONSE_BYTES: Final = 136 * 1024
```

| Claim | Kind | Value | Verdict |
|---|---|---|---|
| `DEFAULT_MAX_RESPONSE_BYTES` | **BOUND — MAY NEVER MOVE** | `136 * 1024` = **139,264** | **HOLDS** |
| the straddle `0 < largest_served_gzipped < ceiling < largest_identity` | **BOUND — MAY NEVER MOVE** | `0 < 129,400 < 139,264 < 457,123` | **HOLDS** |
| exactly **one** identity object refused by the ceiling | **BOUND — MAY NEVER MOVE** | **1** | **HOLDS** |

Measured directly over the package of record, `out/lambda/mainline-demo-api-arm64.zip`:

```
identity (non-.gz) web objects >= 139264 : 1
    web/assets/index-BH5dfAvF.js  = 457123 B
ALL web members >= 139264 (incl .gz)     : 1
STRADDLE  0 < 129400 < 139264 < 457123  -> HOLDS
```

**The distinction that must not be lost:** `139,264` is the **BOUND**. `129,400` and
`457,123` are **MEASUREMENTS of this build** — they are declared in
`tests/deploy/test_furl_compression.py` (`ENTRY_GZIP_BYTES`, `ENTRY_IDENTITY_BYTES`),
`verticals/…/tests/test_response_contract.py` and `…/tests/test_static_site.py`, and a
console rebuild moves all three files' constants together. **What survives a rebuild is
the *shape*: gzipped below the ceiling, identity above it, and exactly one object over.**

Regressions, in descending severity:

1. `DEFAULT_MAX_RESPONSE_BYTES` != `139264` — the ceiling moved. Never acceptable without
   an explicit ruling.
2. The straddle collapses (`gzip >= ceiling`, or `identity <= ceiling`) — the ceiling stops
   refusing anything and becomes a control that controls nothing.
3. The count of identity objects at/over the ceiling stops being **1** — either a second
   oversized chunk appeared, or the only one that proved the ceiling bites went away.

---

## 8. CI at the last pushed commit [LIVE]

```
gh run list --branch master
```

All six workflows triggered by the push of `e88b8b6` (2026-08-14T22:11:25Z):

| workflow | conclusion | run id | verdict |
|---|---|---|---|
| `submission` | **success** | 31845620158 | green |
| `aws-evidence` | **success** | 31845620178 | green |
| `cluster-lane-bites` | **success** | 31845620172 | green |
| `schema` | **failure** | 31845620171 | **RED BY DESIGN** |
| `cluster-tests` | **failure** | 31845620184 | **FIXABLE — see 8.2** |
| `ci` | **failure** | 31845620177 | **mixed — see 8.1** |

### 8.1 `ci` — 12 jobs, 8 green, 3 red + the summary

```
gh run view 31845620177 --json jobs -q '.jobs[] | "\(.conclusion)\t\(.name)"'
```

| job | conclusion | verdict |
|---|---|---|
| every checker this lane invokes exists | success | |
| `actionlint` | success | |
| REUSE — every file names its licence | success | |
| the sequence ban, repository-wide | success | |
| `mypy` · and the target list is complete | success | |
| the lockfile is authoritative · workspace membership | success | |
| import-linter contracts · and no package outside them | success | |
| **RED BY DESIGN, and it must stay red** | **success** | the by-design red is correctly *still* red |
| **PL-2 — the red run is recorded** | **failure** | **RED BY DESIGN** — PL-2 refuses to record another run's URL |
| **ruff format · the counted lint ratchet** | **failure** | **FIXABLE** — the 4 files of §6 |
| **pytest --crdb=none** | **failure** | **FIXABLE** — 2 named tests, below |
| CI summary | failure | aggregate of the above |

The two failing tests in the hermetic pytest job, with their real assertion text:

| test | assertion | verdict |
|---|---|---|
| `tests/release/test_ruff_ratchet.py::test_the_ratchet_passes_on_the_real_tree` | `assert 1 == 0` — *"ratchet refused the tree as committed"* | **FIXABLE** — format the 4 files in §6 |
| `tests/unit/test_row_factory_ratchet.py::test_the_repo_wide_count_may_fall_and_may_not_rise` | `assert 23 <= 16` — *"row-factory debt rose from 16 to 23"* | **FIXABLE — an open regression already in the tree at `e88b8b6`** |

Reproduced locally with `python scripts/qa/row_factory_ratchet.py`:

```
row_factory_ratchet: 23 undeclared row read(s) across 235 parsed file(s) of 1270 scanned
  [inherited_positional_read=16, both_shapes=1, mixed_conventions=4, mutates_connection_row_factory=2]
  openers: 33 with an explicit row_factory (3 hazard unit(s)), 229 on psycopg's default (tuple_row)
  census: 71 module(s) read a borrowed connection positionally
```

**`23` is the number to watch: the ceiling is `16` and the ratchet may fall but may not
rise.** The wave touching demo seed or console transport code can push this higher without
anybody noticing, because the job is *already* red — a red that rises is invisible.

### 8.2 `schema` is red by design; `cluster-tests` is **not**

`schema` — the job prints its own classification, quoted verbatim from the run log:

> `trappoint migrate: REFUSED: 0058_blocking_check: [42P01] relation "trappoint_ref.event" does not exist`
> `RED BY DESIGN, NOT A CI DEFECT. 2 object(s) are referenced by packages/trappoint-sql/refvertical/sql and created by no file in it: trappoint_ref.clause, trappoint_ref.event.`

**This matches the recorded posture exactly.** Owner: KERNEL domain. It turns green only
with a `CREATE TABLE` migration for each object.

`cluster-tests` is **a different animal and must not be filed under "red by design"**:

> `build_lambda: --console-transport is REQUIRED and must be live, replay or both.`

The workflow invokes `scripts/deploy/build_lambda.sh` **without** `--console-transport`,
which commit `b822fdc` made mandatory. The lane fails in its *first* step, so **the
demo-api suite against a real CockroachDB never executed** — the "518 cluster-backed tests"
lane is currently asserting nothing. It has been red this way since `b822fdc`
(31828067342), through `a91a095` (31829388921), to `e88b8b6` (31845620184). **Fix: add the
flag to the workflow.**

### 8.3 Workflows that did not run at `e88b8b6` — last conclusion each

```
gh run list --workflow <name> --branch master --limit 1
```

| workflow | last conclusion | at commit | note |
|---|---|---|---|
| `boundary` | success | `a91a095` | |
| `claims` | success | `0543ff7` | |
| `mutation-ratchet` | success | `3933b97` | |
| `release-proof` | success | `7535670` | |
| `supply-chain` | success | `eefae1c` | |
| `judge-pack` | success | `2dc5c86` | |
| `skills` | success | `2dc5c86` | |
| `custody-chain` | **failure** | `7535670` | **RED BY DESIGN** — 7 of 16 bundle checks unimplemented (§9) |
| `db` | **failure** | `0543ff7` | **RED BY DESIGN** — same missing `trappoint_ref` producers as `schema` |
| `db-schema` | **failure** | `0543ff7` | same family |
| `console` | **failure** | `b822fdc` | did not run at `e88b8b6`; **unknown at this HEAD** |
| `cloud-verify` | **failure** | `3933b97` | did not run at `e88b8b6`; **unknown at this HEAD** |
| `nightly-differential` | **failure** | `3933b97` | |
| **`demo-health`** | **failure** | scheduled, **every run** | **FIXABLE, and the most consequential red in this file — see below** |

#### `demo-health` is red for a stale string, while the demo is live

Every scheduled `demo-health` run fails, most recently 31845482886 at 2026-08-14T22:09Z.
The cause, quoted from the run:

> `read    docs/submission/SUBMISSION.json:demo_url = UNRESOLVED   (sentinel 'UNRESOLVED')`
> `cause   terraform apply has not been run.`

Confirmed against the commit:

```
git show e88b8b6:docs/submission/SUBMISSION.json | grep demo_url
→ "demo_url": "UNRESOLVED",
```

**The stated cause is no longer true.** `terraform apply` *has* been run, the Function URL
exists, and §3 of this file shows it answering `PROVEN` over the public internet. The lane
is not broken — it is correctly refusing to assert against a sentinel. **The consequence is
that nothing in CI has ever asserted the live URL**, and the run says so itself:

> `WHAT WENT UNMEASURED. None of the following was asserted on this run, and none of it is
> asserted anywhere else in CI — this red is the size of that hole, not a reminder to deploy`
> — `GET /`, `GET /v1/health` with a `server_date` fresher than 900 s, and all four beats
> of `POST /v1/demo/gate-run` with `persisted:false` and verdict `PROVEN`.

**This is why §3 of this document is measured by hand.** Until `demo_url` is resolved,
§3 is the *only* record that the live demo works, and it decays the moment the Lambda
changes. Resolving the string turns the lane green on its own and moves §3 from
hand-measured to continuously asserted.

---

## 9. The deployed artefact [WORKTREE build output + LIVE cross-check]

**`out/lambda/mainline-demo-api-arm64.zip` is NOT in `e88b8b6`** — `git ls-files` does not
match it. It is an untracked build output, last written 2026-08-15 04:19 local. Everything
in this section is therefore a **MEASUREMENT of one build**, not a bound, *except* the
cross-check at the end.

```
sha256sum out/lambda/mainline-demo-api-arm64.zip
```

| Claim | Kind | Value |
|---|---|---|
| sha256 (hex) | MEASUREMENT | `6802872f805740dd1a7de891eca7a8d1cf6c11f5eb5b639aec5677f5d78ae13b` |
| sha256 (base64, Lambda's `CodeSha256` form) | MEASUREMENT | `aAKHL4BXQN0afeiR7Keo0c9sEfXrW2Oa7FZ39deK4Ts=` |
| size | MEASUREMENT | **7,721,524 B** |
| members / `web/` members | MEASUREMENT | 250 / 114 |
| **entry chunk** | MEASUREMENT | **`web/assets/index-BH5dfAvF.js`** |
| entry identity bytes | MEASUREMENT | **457,123** |
| entry gzipped bytes (`.gz` sibling) | MEASUREMENT | **129,400** |
| `console.initial` | **BOUND** | **`live`** — *the console starts LIVE* |
| `console.effective` | **BOUND** | `["live", "replay"]` |
| `console.mode` | MEASUREMENT | `demo` |
| **`buildId`** | MEASUREMENT | **`b822fdc`** (with `"unknown"`, which is `honesty.ts`'s `EMPTY` constant and is expected) |
| build command line | **BOUND** | `scripts/deploy/build_lambda.sh --console-transport live` |
| `packer_sha256` | MEASUREMENT | `773de524274915554c6038e2d33d3c16d4e46000b75bd400858c95c93b236825` |

**The console starting LIVE is a BOUND, not a measurement.** A build whose `console.initial`
is `replay` serves a judge a recorded `EvidenceBundle` instead of the kernel the page is
sitting on. `build_lambda.sh` now refuses a build that does not declare
`--console-transport`, which is exactly the guard that broke `cluster-tests` (§8.2) — the
guard is working; the workflow was not updated.

**`buildId` is `b822fdc`, two commits behind `e88b8b6`.** That is consistent and not a
defect: `a91a095` and `e88b8b6` are a test re-record and an evidence commit, neither of
which rebuilds the console.

### The cross-check — deployed bytes are the bytes on disk

```
AWS_PROFILE=mainline-dev aws lambda list-functions --region ap-southeast-1 \
  --query "Functions[].{Name:FunctionName,Sha:CodeSha256,Arch:Architectures[0],Modified:LastModified,Size:CodeSize}"
```

```
arm64  2026-08-14T20:50:43.000+0000  mainline-demo-api  aAKHL4BXQN0afeiR7Keo0c9sEfXrW2Oa7FZ39deK4Ts=  7721524
arm64  2026-08-14T11:43:08.465+0000  mainline-demo-api-guard-responder  rRnOsJbEvD45bERBVx60Ydrd+iCm+854IFySzeZaoZ8=  7366
```

| Claim | Kind | Verdict |
|---|---|---|
| deployed `CodeSha256` == local zip sha256 (base64) | **BOUND — this is the claim** | `aAKHL4BXQN0afeiR7Keo0c9sEfXrW2Oa7FZ39deK4Ts=` on **both sides. EXACT MATCH.** |
| deployed `CodeSize` == local zip size | **BOUND** | `7,721,524` on both sides. **EXACT MATCH.** |
| architecture | **BOUND** | `arm64` |

**This is the load-bearing claim of §9 and the one that survives a rebuild:** whatever the
hashes become, *the artefact on disk and the artefact serving the public URL must be the
same bytes*. If they diverge, `out/lambda/` no longer describes what a judge is looking at,
and every measurement in §7 and §9 is about a file nobody is running.

### Tier 1, the offline bundle — **moved since `VERIFY.md` was written**

```
.venv/Scripts/trappoint-verify.exe verify --bundle evidence/reference-ledger/bundle.json
```

```
16 checks | 9 passed | 0 failed | 7 not checked
exit 2: everything that ran held, and 7 check(s) did not run. This is NOT a clean verification.
```

| | `VERIFY.md` records | **Measured** |
|---|---|---|
| checks | 16 | 16 |
| passed | 8 | **9** |
| failed | **1** (`canonicaliser_identity`, real drift) | **0** |
| not checked | 7 | 7 |
| exit | **1** | **2** |

**The canonicaliser drift that `VERIFY.md` documents at length has been repaired**, and the
exit code moved `1 → 2` — a different code meaning *"everything that ran held, but seven
did not run"*. This is the `custody-chain` **7 of 16**, and it remains **RED BY DESIGN**:
the seven unimplemented checks are the cryptographic half (log signature, RFC-3161
timestamp bracket, beacon, witness quorum, S3 object-lock, gate self-attestation, WebAuthn).
`docs/VERIFY.md` §Tier 1 is now **stale** and describes a failure that no longer occurs.

---

## 10. The one-line regression sweep

For someone who was not here and has ten minutes, in this order:

```bash
cd D:/CoackroachDBxAWS/mainline
PY=D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe
URL=https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws

# 1. the live demo still proves itself (fastest, highest signal)
curl -sS "$URL/v1/health" | grep -o '"ok":true'
curl -sS -X POST -H 'content-type: application/json' -d '{}' "$URL/v1/demo/gate-run" | grep -o '"verdict": *"PROVEN"'

# 2. the bounds
grep -n "DEFAULT_MAX_RESPONSE_BYTES: Final" verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py
# must print: 136 * 1024

# 3. the local refusal still reproduces  (~3 min on a quiet box)
$PY scripts/proof/gate_refusal.py --dsn "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
# must print: VERDICT PROVEN, chain 271/271, caveats (none)

# 4. the suite still collects
$PY -m pytest verticals/mainline/apps/demo-api/tests tests/deploy --crdb=none --collect-only -q | tail -1
# must print: 911 tests collected

# 5. the ratchets
$PY scripts/qa/ruff_ratchet.py          # LINT regressions must be 0
$PY scripts/qa/row_factory_ratchet.py   # must not exceed 23; ceiling is 16

# 6. deployed bytes == local bytes
AWS_PROFILE=mainline-dev aws lambda get-function-configuration \
  --function-name mainline-demo-api --region ap-southeast-1 --query CodeSha256
```

---

## 11. What did NOT reproduce

**Three things.** Each is recorded here rather than smoothed over. A fourth — the suite
baseline — reproduced exactly but only under a changed condition, and is listed first so it
is not mistaken for a clean pass.

### 11.0 The `911 / 910 / 0 / 0 / 1` baseline — reproduced **exactly**, with a caveat

All five junit numbers matched and the one skip was the expected `jsonschema` one (§2.2).
**But it took `--timeout=900` to get there**: at the committed `timeout = 120`, the suite
was killed in the `_w1_built` fixture on both attempts, because that fixture applies the
271-file chain and the chain currently takes 146 s on this loaded box. Nothing in the code
regressed. **Anyone re-running this while the wave is active should raise the timeout
before concluding anything**, and should treat a `+++ Timeout +++` stack ending in
`apply_chain` as an environment reading rather than a defect.

### 11.1 `mainline_api` `SELECT` — recorded **66**, measured **69**

Everything else in the privilege census matched exactly (CONNECT 1, USAGE 37, UPDATE 3,
INSERT 8, EXECUTE 29), which makes a measurement error unlikely: five of six categories
reproducing and one moving by +3 reads as a real change to the grant set, not a miscount.

**Which three cannot be recovered**, because the recorded baseline was a bare count with no
object list. §5 now carries all 69 by name so the same question is answerable next time.
This is a **[LIVE]** reading and the cloud cluster can be re-granted without any commit.

### 11.2 `docs/VERIFY.md` Tier 1 — records `8 passed / 1 failed / exit 1`, measured `9 passed / 0 failed / exit 2`

See §9. The direction is *good* — a real canonicaliser drift was repaired — but the
document was not updated, so the page a stranger is told to lead with describes a failure
that no longer happens. The seven unchecked checks are unchanged and still red by design.

### 11.3 `docs/VERIFY.md` "What none of this proves" — a claim that is now false

The page states, as of its 2026-08-12 revision:

> *"Not that any AWS service other than Bedrock has run. … Lambda, CloudFront, S3, KMS, IAM
> roles and SSM are designed and unapplied — `terraform apply` has never been run — which is
> also why there is no demo URL to point you at."*

**`terraform apply` has been run.** A Lambda exists, a Function URL answers over the public
internet, and §3 records it returning `PROVEN`. The same stale premise is what keeps
`demo_url` at `UNRESOLVED` in `docs/submission/SUBMISSION.json` and `demo-health` red on
every schedule (§8.3). **This is a documentation regression, and it is the one most likely
to mislead a judge**, because `VERIFY.md` is the page the README sends strangers to first.

---

## 12. Provenance of this file

Written by a read-only worker whose only write was this file. Nothing was committed,
stashed, checked out or restored; no `terraform apply`, no redeploy, no mutating AWS call
was made; every AWS and `gh` call was a read; every cloud SQL statement was a `SELECT` or a
`SHOW`, issued on a `read_only` connection; and no DSN, password or credential appears
anywhere above.

The one deliberate deviation from a pure observation is in §2.2, where `--timeout` was
raised above the value in `pyproject.toml` in order to obtain a number at all; it is
declared there rather than folded silently into the result.
