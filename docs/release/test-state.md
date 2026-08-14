<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Test state — the census

**Generated file. Do not edit.** Every number here is read out of
[`qa/test-state.json`](../../qa/test-state.json), written by
[`scripts/qa/report_test_state.py`](../../scripts/qa/report_test_state.py).
Re-derive the whole document in one command:

```
python scripts/qa/report_test_state.py
```

Taken `2026-08-09T22:44:59Z` with `pytest 9.1.1` on Python 3.13.14 (win32), 2414.6 s of wall clock.

**Some rows were re-measured after that timestamp** and the totals recomputed from every row present. Nothing is carried forward.

* `2026-08-09T23:27:46Z` — `tests/integration`, `--crdb=reuse`, ceiling 2400 s
* `2026-08-09T23:35:43Z` — `tests/integration`, `--crdb=none`, ceiling 600 s
* `2026-08-09T23:38:55Z` — `tests/release`, `--crdb=none`, `--crdb=reuse`, ceiling 600 s
* `2026-08-13T11:22:26Z` — `verticals/mainline/apps/demo-api`, `--crdb=none`, `--crdb=reuse`, ceiling 900 s
* `2026-08-13T11:39:20Z` — `verticals/mainline/apps/demo-api`, `--crdb=reuse`, ceiling 900 s
* `2026-08-13T11:45:26Z` — `verticals/mainline/apps/demo-api`, `--crdb=reuse`, ceiling 900 s, dialled `127.0.0.1:26257`
* `2026-08-13T11:50:38Z` — `verticals/mainline/apps/demo-api`, `--crdb=reuse`, ceiling 900 s, dialled `127.0.0.1:26257`

Cluster pass ran against `<dsn>` — CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5), `gc.ttlseconds = 14400`.

> ## ⚠ STALE, AND DELIBERATELY NOT RE-TYPED — annotated 2026-08-14 by D3
>
> **This is a generated file and it says so: *"Generated file. Do not edit."*** Every number
> below is read out of `qa/test-state.json` by `scripts/qa/report_test_state.py`. **The
> correct repair is to re-run that generator, not to hand-edit a row**, and the generator
> writes into `qa/`, which the DOCS-TRUE wave does not own. So this file is annotated and its
> digits are left untouched.
>
> **What is known to have moved, with today's measurement beside it:**
>
> | row | this file (2026-08-09 → 08-13) | measured 2026-08-14 by D3 |
> |---|---|---|
> | `verticals/mainline/apps/demo-api`, `--crdb=reuse` | folded into a `--crdb=reuse` total of `7632 / 7340P / 30F / 245E / 17S` | **576 tests · 575 passed · 0 failed · 0 errors · 1 skipped**, `217.7 s` |
>
> Read from `--junitxml`'s `<testsuite>` attributes, never a terminal scroll:
>
> ```
> $ MAINLINE_W4_DATABASE=w_D3 .venv/Scripts/python.exe -m pytest \
>       verticals/mainline/apps/demo-api/tests --crdb=reuse -q -p no:randomly \
>       --junitxml=out/qa/D3-before2.xml
> 575 passed, 1 skipped in 218.45s (0:03:38)
> tests=576  failures=0  errors=0  skipped=1
> ```
>
> The one skip is `test_gate_run.py:1294` — *"jsonschema is not a workspace dependency"*.
>
> **A measurement hazard worth naming, because it corrupted a reading in this very wave.**
> The demo-api suite's scratch database is named from a **fingerprint of its own inputs**
> (`test_gate_run.py:259`), so two workers running the suite against the same node on the
> same tree get the *same* database. A first attempt at the reading above, taken while
> another worker's suite was live, reported **1 failed** — and the failing test was
> `test_a_concurrent_committer_moves_the_counts_and_is_not_this_runs_failure`, which observed
> `mainline.permit` moving by **+2** where it requires **+1**. The test was right: there *was*
> a concurrent committer. The clean reading was taken with the sanctioned
> `MAINLINE_W4_DATABASE` override, which `test_gate_run.py:255-258` keeps for exactly this
> purpose. **Both readings are reported here. A number taken under contention is not a
> number, and quietly discarding the first one would have been the more flattering choice.**
>
> **The rest of the table below is not re-derived and may have moved in either direction.**
> Re-run `python scripts/qa/report_test_state.py` to replace it wholesale; do not patch a
> cell.

## Totals

| pass | targets | tests | passed | failed | errored | skipped | xfailed | timed out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `--crdb=none` | 27 | 9290 | 8323 | 44 | 0 | 923 | 0 | 0 |
| `--crdb=reuse` | 27 | 7632 | 7340 | 30 | 245 | 17 | 0 | 1 |

`P` passed · `F` failed · `E` errored (including collection errors) · `S` skipped ·
`X` xfailed. A bold count is non-zero.

## Per target

| target | kind | `--crdb=none` | `--crdb=reuse` |
|---|---|---|---|
| `packages/mainline-agentkit` | distribution | 129P | 129P |
| `packages/mainline-boundary` | distribution | 54P **1F** | 54P **1F** |
| `packages/mainline-mcp` | distribution | 147P | 147P |
| `packages/trappoint-conformance` | distribution | 24P 183S | 24P **182E** 1S |
| `packages/trappoint-core` | distribution | 56P | 56P |
| `packages/trappoint-diagnose` | distribution | 126P 17S | 126P **14F** 3S |
| `packages/trappoint-jcs` | distribution | 82P | 82P |
| `packages/trappoint-ledger` | distribution | 285P | 285P |
| `packages/trappoint-migrate` | distribution | 216P **1F** | 216P **1F** |
| `packages/trappoint-model` | distribution | 22P 11S | 33P |
| `packages/trappoint-sql` | distribution | 131P | 131P |
| `packages/trappoint-testkit` | distribution | 26P 2S | 28P |
| `packages/trappoint-verify` | distribution | 88P | 88P |
| `verticals/mainline/packages/mainline-anchor` | distribution | 59P | 59P |
| `verticals/mainline/packages/mainline-custody-patrol` | distribution | 28P | 28P |
| `verticals/mainline/packages/mainline-gate-svc` | distribution | 61P | 61P |
| `verticals/mainline/packages/mainline-sequencer` | distribution | 59P | 59P |
| `tests/agents` | test-root | 54P | 54P |
| `tests/boundary` | test-root | 115P **1F** 6S | 115P **1F** 6S |
| `tests/concurrency` | test-root | 20P 16S | 35P 1S |
| `tests/e2e` | test-root | 967P | 967P |
| `tests/eval` | test-root | 166P **5F** | 166P **5F** |
| `tests/integration` | test-root | 1141P **29F** 488S | **TIMED OUT** |
| `tests/release` | test-root | 119P **4F** 8S | 127P **4F** |
| `tests/security` | test-root | 458P **1F** 2S | 458P **1F** 2S |
| `tests/unit` | test-root | 3432P **2F** 3S | 3432P **2F** 3S |
| `verticals/mainline/apps/demo-api` | distribution | 258P 187S | 380P **1F** **63E** 1S |

## Every skip reason — `--crdb=none` pass

| count | reason string, verbatim |
|---:|---|
| 211 | no cluster: set TRAPPOINT_DSN (or LOCAL_DSN). For a local single-node node — `docker compose up -d crdb` then TRAPPOINT_DSN=<dsn> |
| 187 | the session obtained no CockroachDB, so this cluster-backed test is skipped rather than allowed to reach a node the session declined to obtain. trappoint-testkit says: --crdb=none: this session declined to obtain a CockroachDB, so every test that needs one is skipped rather than allowed to start a private container |
| 183 | SKIP WITH REASON: no TRAPPOINT_DSN or LOCAL_DSN. These assertions are about what a database does; without one there is nothing to assert and pretending otherwise would be a suite that passes by absence. `just up && just migrate`. |
| 36 | no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or start the Docker daemon so the suite can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. Decision D8 is NOT verified by a skipped run. |
| 31 | no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or start the Docker daemon so the suite can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. CONSERVATION OF BLAME MASS is NOT verified by a skipped run. |
| 26 | no live CockroachDB: none of MAINLINE_TEST_DSN, COCKROACH_URL, CRDB_URL is set and no `cockroach` binary is on PATH. The offline half of this suite still ran; the plan and SQL-equivalence claims are UNVERIFIED. |
| 24 | no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or start the Docker daemon so the suite can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. The recall band is NOT verified by a skipped run. |
| 19 | no CockroachDB v26.2 reachable. Provide $MAINLINE_TEST_DSN, a `cockroach` binary on PATH, or a running Docker daemon for `docker run cockroachdb/cockroach:v26.2.5`. Migrations 0037-0039 and queries/closure_write.sql are NOT verified by a skipped run. |
| 19 | no Managed-MCP credential: set MAINLINE_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID (or CC_API_KEY and CRDB_CLUSTER). This suite SKIPS rather than passes — a negative suite that goes green without ever trying asserts the opposite of what it claims. |
| 18 | no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or start the Docker daemon so the suite can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. ORIGINDIFF's view is NOT verified by a skipped run. |
| 15 | SKIP(no-cluster): no CockroachDB v26.2 reachable. Set MAINLINE_TEST_DSN to a LOCAL cluster, or put `cockroach` on PATH, or start the Docker daemon so the lane can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. NO ATTACK WAS EXECUTED AND NO DETECTION WAS OBSERVED BY A SKIPPED RUN — the matrix such a run could produce would be spec/custody/attacks.yaml with a different layout, which is a list of expectations, not a record. |
| 15 | no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or start the Docker daemon so the suite can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. The claim that the vector index is used is NOT proven by a skipped run. |
| 15 | no CockroachDB v26.2 reachable: set TRAPPOINT_DSN, or put `cockroach` on PATH, or start the Docker daemon so the lane can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. A SKIPPED RUN IS NOT EVIDENCE: the gate is a database mechanism and nothing in this package can stand in for it. |
| 14 | TRAPPOINT_DSN is unset; this case needs a migrated cluster |
| 14 | no CockroachDB v26.2 reachable. Provide $MAINLINE_TEST_DSN, a `cockroach` binary on PATH, or a running Docker daemon for `docker run cockroachdb/cockroach:v26.2.5`. Migrations 0032-0036 are NOT verified by a skipped run. |
| 12 | no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or start the Docker daemon so the suite can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. Migration 0207 is NOT verified by a skipped run. |
| 11 | no Managed-MCP credential: set MAINLINE_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID (or CC_API_KEY and CRDB_CLUSTER). This suite SKIPS rather than passes, because a green audit-surface run with nothing to talk to would assert nothing. |
| 10 | no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or start the Docker daemon. SQLite cannot stand in here — its planner is not CockroachDB's, so a green SQLite run would say nothing about whether the optimiser constrained the scan. Channel D's PLAN is NOT verified by this skipped run. |
| 9 | SKIP(no-cluster): no CockroachDB v26.2 reachable. Set MAINLINE_TEST_DSN to a LOCAL cluster, or put `cockroach` on PATH, or start the Docker daemon so the lane can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. IDEMPOTENCE AND ledger_linear ARE NOT VERIFIED BY A SKIPPED RUN — both are database refusals and nothing in process can stand in for them. |
| 8 | no cluster DSN. Set one of MAINLINE_TEST_DSN, TRAPPOINT_DSN, COCKROACH_URL, CRDB_URL, LOCAL_DSN to run the release proof. |
| 7 | no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or start the Docker daemon so the lane can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. THE EPOCH PIN IS NOT VERIFIED BY A SKIPPED RUN — the agent-side tests in this file still ran, and they assert the client contract only. |
| 7 | no cluster: set one of MAINLINE_TEST_DSN, COCKROACH_URL, CRDB_URL, TRAPPOINT_DSN. AWS credentials are not valid on this build machine, so a local `cockroach` binary or a container is the intended path |
| 4 | SKIP(no-cluster): no CockroachDB v26.2 reachable. Set MAINLINE_TEST_DSN to a LOCAL cluster, or put `cockroach` on PATH, or start the Docker daemon so the lane can run `docker run cockroachdb/cockroach:v26.2.5 start-single-node --insecure`. DENSITY AND FORK-FREEDOM ARE NOT VERIFIED BY A SKIPPED RUN — they are properties of two database constraints under real concurrency. |
| 3 | TRAPPOINT_DSN is unset; this case needs a migrated cluster and a refused permit |
| 3 | no cluster: set one of MAINLINE_TEST_DSN, TRAPPOINT_DSN, COCKROACH_URL, CRDB_URL. For a local single-node node — `cockroach start-single-node --insecure` — that is TRAPPOINT_DSN=<dsn> This is a SKIP and not a pass: the schema fingerprint's stability against a REAL `SHOW CREATE ALL …` is K2 exit criterion 6, and a fake cannot prove it. |
| 2 | --crdb=none: this session declined to obtain a CockroachDB, so every test that needs one is skipped rather than allowed to start a private container |
| 2 | neither `conftest` nor `opa` is on PATH, so the Rego re-statement of E1/E2/E4 was not evaluated. The Python assertions in this suite still stand; the independent second opinion does not. CI installs conftest, so this skip cannot occur there. |
| 2 | refused before the pipeline runs; covered by test_layers.py |
| 1 | N=64 is the nightly arm: set TRAPPOINT_NIGHTLY=1. It is skipped rather than scaled down because a 64-way race that quietly ran 8-way would report a contention level nobody measured. |
| 1 | SKIP(no-cluster): reads the live schema for row-level TTL on any ledger_* table. |
| 1 | SKIP(no-cluster): requires a disposable single-node CockroachDB. Green from K2 onward via tests/integration/custody/nemesis/test_gate_attacks.py. |
| 1 | TAXONOMY INTEGRATION LANE OWED: migrations ['0032_activity_node.sql', '0033_event.sql'] have landed, so mainline.activity_node and mainline.event now exist and the LMB/bond writers can be exercised against a real cluster. This lane must be built against them (apply the migrations, insert a fonds / series / file chain and an event, run LevelMaterialisedBondWriter and BondWriter, assert the row counts and the unique-constraint behaviour). Until then the writers are proven only by the unit suite. |
| 1 | insert_rows is a real append to a real evidentiary table; set MAINLINE_MCP_ALLOW_WRITE=1 to exercise it, and only against mainline-verify |
| 1 | live IAM simulation not attempted: MAINLINE_BOUNDARY_LIVE_AWS is not set to 1. The plan-time assertions in this module still hold; this one does not, and is not counted as a pass. |
| 1 | live IAM simulation unavailable: MAINLINE_BOUNDARY_LIVE_AWS is not set to 1 |
| 1 | mainline-delta-oracle is installed in this environment; the AST checks still prove the lattice does not import it, but the stronger 'it is not even here' claim is not available from this run |
| 1 | no Managed-MCP credential: set CC_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID. This SKIPS rather than passing, because a green attest run with nothing to talk to would assert nothing about the one write path this package has. |
| 1 | no Managed-MCP credential: set CC_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID. This SKIPS rather than passing, because a green attest run with nothing to talk to would assert nothing about the one write path this package has. The write additionally requires MAINLINE_STEWARD_SEND=1, because insert_rows is a real append to a real evidentiary table and a test run is not a reason to add a row to one. |
| 1 | no kernel-image SBOM is committed at evidence/sbom/kernel/current.cdx.json, so the image contents are unproven. NOT A PASS. Reason: no SBOM for the current kernel image is committed, so the image contents are unproven. The AST scan still stands on its own; this leg does not. |
| 1 | pyproject.toml does not declare 'trappoint-recall-verify-per'. It is one line in a file owned by recall-eval-harness: trappoint-recall-verify-per = "trappoint_recall.per.cli:main" under [project.scripts]. Reported rather than assumed; the reference invocation 'python -m trappoint_recall.per' is asserted by the tests above and works today. |
| 1 | sentence-transformers is the 'local-embed' extra and the bge-large weights are a network fetch; neither is available offline. Install the extra, warm the cache, then run with MAINLINE_BGE_REVISION set. |
| 1 | spec/agents/fleet.yaml does not exist yet (owned by the agent-contracts-red worker), so the matrix below is asserted against the reference register at packages/mainline-boundary/tests/fixtures/fleet_reference.yaml. NOT A PASS for the shipped fleet. |
| 1 | the repository README makes no Proof-of-Exhausted-Recall claim yet, so it owes no bound. The grep starts biting the moment it does. |
| 1 | unattended `ccloud` auth is undocumented (§9.3: --no-redirect exists for headless login; no API-key flag or environment variable is published), and this build has no CockroachDB Cloud organisation. Set MAINLINE_STEWARD_CCLOUD_LIVE=1 with a logged-in ccloud to exercise it. This SKIPS rather than passing, because a green live lane with nothing to talk to would assert nothing. |

## Every skip reason — `--crdb=reuse` pass

| count | reason string, verbatim |
|---:|---|
| 3 | TRAPPOINT_REFUSED_PERMIT is unset; this case needs a migrated cluster and a refused permit |
| 2 | neither `conftest` nor `opa` is on PATH, so the Rego re-statement of E1/E2/E4 was not evaluated. The Python assertions in this suite still stand; the independent second opinion does not. CI installs conftest, so this skip cannot occur there. |
| 2 | refused before the pipeline runs; covered by test_layers.py |
| 1 | N=64 is the nightly arm: set TRAPPOINT_NIGHTLY=1. It is skipped rather than scaled down because a 64-way race that quietly ran 8-way would report a contention level nobody measured. |
| 1 | SKIP WITH REASON: the cluster holds none of the gate's objects, so there is no source text to attest. Run `just migrate` first. |
| 1 | TAXONOMY INTEGRATION LANE OWED: migrations ['0032_activity_node.sql', '0033_event.sql'] have landed, so mainline.activity_node and mainline.event now exist and the LMB/bond writers can be exercised against a real cluster. This lane must be built against them (apply the migrations, insert a fonds / series / file chain and an event, run LevelMaterialisedBondWriter and BondWriter, assert the row counts and the unique-constraint behaviour). Until then the writers are proven only by the unit suite. |
| 1 | jsonschema is not a workspace dependency; the structural check above is what runs today and this turns green the day it is added |
| 1 | live IAM simulation not attempted: MAINLINE_BOUNDARY_LIVE_AWS is not set to 1. The plan-time assertions in this module still hold; this one does not, and is not counted as a pass. |
| 1 | live IAM simulation unavailable: MAINLINE_BOUNDARY_LIVE_AWS is not set to 1 |
| 1 | mainline-delta-oracle is installed in this environment; the AST checks still prove the lattice does not import it, but the stronger 'it is not even here' claim is not available from this run |
| 1 | no kernel-image SBOM is committed at evidence/sbom/kernel/current.cdx.json, so the image contents are unproven. NOT A PASS. Reason: no SBOM for the current kernel image is committed, so the image contents are unproven. The AST scan still stands on its own; this leg does not. |
| 1 | sentence-transformers is the 'local-embed' extra and the bge-large weights are a network fetch; neither is available offline. Install the extra, warm the cache, then run with MAINLINE_BGE_REVISION set. |
| 1 | spec/agents/fleet.yaml does not exist yet (owned by the agent-contracts-red worker), so the matrix below is asserted against the reference register at packages/mainline-boundary/tests/fixtures/fleet_reference.yaml. NOT A PASS for the shipped fleet. |

## What is red

### `packages/mainline-boundary` — `--crdb=none`

exit `1` (tests were collected and at least one failed), 1 failed, 0 errored.

* `packages.mainline-boundary.tests.test_cli::test_greps_pass_over_the_repository`

### `packages/mainline-boundary` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 1 failed, 0 errored.

* `packages.mainline-boundary.tests.test_cli::test_greps_pass_over_the_repository`

### `packages/trappoint-conformance` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 0 failed, 182 errored.

* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-01]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-02]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-03]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-04]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-05]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-06]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-07]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-08]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-09]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-10]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-11]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-12]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-13]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-14]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-15]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-16]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-17]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-18]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-19]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-20]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-21]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-23]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-25]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-26]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-27]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-28]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-29]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-30]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-31]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-32]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-33]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-34]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-36]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-37]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-38]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-39]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-40]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-41]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-42]`
* `packages.trappoint-conformance.tests.test_conformance_cases::test_case_outcome_class[CF-43]`
* … more than 40 named; see the JSON.

### `packages/trappoint-diagnose` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 14 failed, 0 errored.

* `tests.test_live_ledger::test_a_refusal_can_be_recorded`
* `tests.test_live_ledger::test_the_ledger_is_append_only[UPDATE]`
* `tests.test_live_ledger::test_the_ledger_is_append_only[DELETE]`
* `tests.test_live_ledger::test_a_reason_set_that_is_not_an_array_is_refused`
* `tests.test_live_ledger::test_an_atom_key_outside_the_closed_vocabulary_is_refused`
* `tests.test_live_ledger::test_an_atom_naming_no_modelled_fact_family_is_refused`
* `tests.test_live_ledger::test_a_row_that_disagrees_with_its_own_payload_is_refused[mutate0-refusal_payload_names_the_exhibit]`
* `tests.test_live_ledger::test_a_row_that_disagrees_with_its_own_payload_is_refused[mutate1-refusal_payload_names_the_code]`
* `tests.test_live_ledger::test_a_row_that_disagrees_with_its_own_payload_is_refused[mutate2-refusal_payload_names_the_diagnosis]`
* `tests.test_live_ledger::test_a_row_that_disagrees_with_its_own_payload_is_refused[mutate3-refusal_mus_agrees]`
* `tests.test_live_ledger::test_a_row_that_disagrees_with_its_own_payload_is_refused[mutate4-refusal_payload_names_the_alternative]`
* `tests.test_live_ledger::test_a_declarative_diagnosis_that_probed_is_refused_by_the_table_too`
* `tests.test_live_ledger::test_a_payload_carrying_a_person_metric_is_refused_by_a_plain_column_check`
* `tests.test_live_ledger::test_a_p0001_refusal_recorded_as_reported_is_refused`

### `packages/trappoint-migrate` — `--crdb=none`

exit `1` (tests were collected and at least one failed), 1 failed, 0 errored.

* `tests.test_lockfile::test_the_committed_manifest_is_current`

### `packages/trappoint-migrate` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 1 failed, 0 errored.

* `tests.test_lockfile::test_the_committed_manifest_is_current`

### `tests/boundary` — `--crdb=none`

exit `1` (tests were collected and at least one failed), 1 failed, 0 errored.

* `tests.boundary.test_ci_greps::test_no_request_builder_sets_a_sampling_parameter`

### `tests/boundary` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 1 failed, 0 errored.

* `tests.boundary.test_ci_greps::test_no_request_builder_sets_a_sampling_parameter`

### `tests/eval` — `--crdb=none`

exit `1` (tests were collected and at least one failed), 5 failed, 0 errored.

* `tests.eval.recall.test_g4alpha_gates::test_retro_recall_at_3_on_severity_5`
* `tests.eval.recall.test_g4alpha_gates::test_precision_at_block`
* `tests.eval.recall.test_g4alpha_gates::test_nuisance_rate`
* `tests.eval.recall.test_g4alpha_gates::test_mean_blocking_checks_per_permit`
* `tests.eval.recall.test_g4alpha_gates::test_silence_conservation_law`

### `tests/eval` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 5 failed, 0 errored.

* `tests.eval.recall.test_g4alpha_gates::test_retro_recall_at_3_on_severity_5`
* `tests.eval.recall.test_g4alpha_gates::test_precision_at_block`
* `tests.eval.recall.test_g4alpha_gates::test_nuisance_rate`
* `tests.eval.recall.test_g4alpha_gates::test_mean_blocking_checks_per_permit`
* `tests.eval.recall.test_g4alpha_gates::test_silence_conservation_law`

### `tests/integration` — `--crdb=reuse`

exit `None` (the target did not finish within 2400s of wall clock and was killed by report_test_state.py; nothing below it was measured), 0 failed, 0 errored, **timed out**.


### `tests/integration` — `--crdb=none`

exit `1` (tests were collected and at least one failed), 29 failed, 0 errored.

* `tests.integration.algorithms.registry.test_0207_shape::test_the_migration_is_exactly_one_statement`
* `tests.integration.algorithms.registry.test_0207_shape::test_the_header_declares_what_the_band_requires`
* `tests.integration.algorithms.registry.test_0207_shape::test_the_algorithms_band_holds_only_this_worker_s_file_at_0207`
* `tests.integration.algorithms.registry.test_0207_shape::test_the_view_name_and_schema_are_the_reserved_ones`
* `tests.integration.algorithms.registry.test_0207_shape::test_the_sql_labels_match_the_python_grammar`
* `tests.integration.algorithms.registry.test_0207_shape::test_every_ratifiable_direction_is_named_in_the_answers_predicate`
* `tests.integration.algorithms.registry.test_0207_shape::test_the_migration_says_out_loud_that_it_is_not_what_the_gate_reads`
* `tests.integration.algorithms.registry.test_0207_shape::test_the_migration_claims_no_refusal_it_does_not_implement`
* `tests.integration.custody.nemesis.test_ledger_attacks::test_fixture_names_the_same_constraints_as_the_migrations`
* `tests.integration.custody.test_k2_exit::test_k2_1_tamper_is_caught_by_a_consistency_proof`
* `tests.integration.custody.test_k2_exit::test_k2_2_closure_rewrite_is_caught_by_check_14`
* `tests.integration.custody.test_k2_exit::test_k2_4_checkpoint_cadence_measured_and_deadman_defined`
* `tests.integration.custody.test_k2_exit::test_k2_5_checkpoint_wire_format_tagged_v1_0_with_changelog_entry`
* `tests.integration.custody.test_k2_exit::test_k2_6_migration_attestation_chained_with_a_stable_fingerprint`
* `tests.integration.custody.test_k2_exit::test_verifier_determinism`
* `tests.integration.recall_run.test_claim_bound_grep::test_the_wide_ring_holds_the_claim_unchanged`
* `tests.integration.recall_schema.test_rc00_migration_shape::test_rc00g_a_trigger_function_only_names_columns_its_own_table_has`
* `tests.integration.schema.test_mi_blame::test_dm9_the_closure_is_read_only_through_the_view`
* `tests.integration.schema.test_mi_blame::test_pl2_red_sev_max_is_never_projected_from_the_closure`
* `tests.integration.schema.test_mi_blame::test_mi26_red_the_monotone_guard_accepts_an_unrelated_severity_revision`
* `tests.integration.schema.test_mi_boundary_override::test_pl2_red_fn_boundary_project_does_not_exist_yet`
* `tests.integration.schema.test_mi_boundary_override::test_pl2_red_the_carried_use_projection_does_not_exist_yet`
* `tests.integration.schema.test_mi_boundary_override::test_pl2_red_the_two_new_evidentiary_tables_have_no_append_only_trigger`
* `tests.integration.schema.test_mi_boundary_override::test_pl2_red_nothing_yet_requires_a_cited_predicate_to_still_be_holding`
* `tests.integration.schema.test_mi_disposition_gated::test_every_counsel_gated_object_declares_it[mainline_meas.silence_ledger]`
* `tests.integration.schema.test_mi_event_severity::test_pl2_red_severity_revision_provenance_is_not_yet_projected`
* `tests.integration.schema.test_mi_ratchet::test_red_every_invariant_is_enforced`
* `tests.integration.schema.test_mi_spine::test_band_is_exactly_the_declared_files`
* `tests.integration.schema.test_mi_spine::test_no_filename_in_the_tree_defeats_the_runners_version_regex`

### `tests/release` — `--crdb=none`

exit `1` (tests were collected and at least one failed), 4 failed, 0 errored.

* `tests.release.test_honesty_is_checkable::test_every_quantity_equals_the_value_it_cites`
* `tests.release.test_honesty_is_checkable::test_no_citation_is_decorative`
* `tests.release.test_mypy_covers_workspace::test_check_passes_on_the_real_tree`
* `tests.release.test_mypy_covers_workspace::test_ratchet_records_every_distribution_and_the_mypy_version`

### `tests/release` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 4 failed, 0 errored.

* `tests.release.test_honesty_is_checkable::test_every_quantity_equals_the_value_it_cites`
* `tests.release.test_honesty_is_checkable::test_no_citation_is_decorative`
* `tests.release.test_mypy_covers_workspace::test_check_passes_on_the_real_tree`
* `tests.release.test_mypy_covers_workspace::test_ratchet_records_every_distribution_and_the_mypy_version`

### `tests/security` — `--crdb=none`

exit `1` (tests were collected and at least one failed), 1 failed, 0 errored.

* `tests.security.injection.test_layers::test_scanner_is_green_on_the_real_tree`

### `tests/security` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 1 failed, 0 errored.

* `tests.security.injection.test_layers::test_scanner_is_green_on_the_real_tree`

### `tests/unit` — `--crdb=none`

exit `1` (tests were collected and at least one failed), 2 failed, 0 errored.

* `tests.unit.domain.novelty.test_novelty_manifest::test_every_cited_test_path_exists[deltalattice]`
* `tests.unit.domain.novelty.test_novelty_manifest::test_every_implementation_path_exists[directrix]`

### `tests/unit` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 2 failed, 0 errored.

* `tests.unit.domain.novelty.test_novelty_manifest::test_every_cited_test_path_exists[deltalattice]`
* `tests.unit.domain.novelty.test_novelty_manifest::test_every_implementation_path_exists[directrix]`

### `verticals/mainline/apps/demo-api` — `--crdb=reuse`

exit `1` (tests were collected and at least one failed), 1 failed, 63 errored.

* `tests.test_reads::test_an_undeclared_query_parameter_is_refused_rather_than_ignored`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[audit]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[blocking_checks]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[change_request]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[clause_ancestry]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[clause_version]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[disposition]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[exposure_receipt]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[ledger]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[permit]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[propagation]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[recall_run]`
* `tests.test_reads::test_every_read_satisfies_its_committed_contract[silence]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[audit]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[blocking_checks]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[change_request]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[clause_ancestry]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[clause_version]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[disposition]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[exposure_receipt]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[ledger]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[permit]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[propagation]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[recall_run]`
* `tests.test_reads::test_every_read_survives_the_clients_own_post_conditions[silence]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[audit]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[blocking_checks]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[change_request]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[clause_ancestry]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[clause_version]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[disposition]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[exposure_receipt]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[ledger]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[permit]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[propagation]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[recall_run]`
* `tests.test_reads::test_every_provenance_pointer_addresses_something_real[silence]`
* `tests.test_reads::test_no_read_silently_drops_a_provenance_claim[audit]`
* `tests.test_reads::test_no_read_silently_drops_a_provenance_claim[blocking_checks]`
* `tests.test_reads::test_no_read_silently_drops_a_provenance_claim[change_request]`
* `tests.test_reads::test_no_read_silently_drops_a_provenance_claim[clause_ancestry]`
* … more than 40 named; see the JSON.


## Checks a stranger runs that pytest does not collect

### `custody_bundle_verification`

trappoint-verify, offline, over the committed reference ledger — the Tier-1 verification in VERIFY.md, the one that needs no credential at all

```
python -m trappoint_verify.cli verify --bundle evidence/reference-ledger/bundle.json --json
```

exit `2` — everything that ran held, and at least one check did not run.

**9 passed, 0 failed, 7 not checked**, of 16 checks.

Not checked: `4 log_signature`, `5 rfc3161_upper_bound`, `6 beacon_lower_bound`, `7 witness_quorum`, `8 archive_object_lock`, `11 gate_self_attestation`, `12 webauthn_reverification`


## Where this ran, and why every duration above is a LOCAL duration

| fact | value | measured by this script? |
|---|---|---|
| DDL + 5000 `VECTOR(256)` inserts, local node | **11.802 s** (5.319 s DDL + 6.483 s inserts) | yes |
| 9 DDL statements on CockroachDB Cloud Basic (Singapore) | >120 s | **no** — transcribed from `docs/leads/kernel.md line 311` |
| inference region | `ap-southeast-2 (Sydney) — 8 au.* Claude inference profiles` | **no** — recorded in `docs/adr/0002-g1-platform-ground-truth.md` |
| database region (Cloud) | `aws-ap-southeast-1 (Singapore), Basic tier` | **no** — same |
| Bedrock Rerank in `ap-southeast-2` | **not available** | **no** — same |
| end-to-end Australian data residency | **no** | **no** — same |

The cross-region hop between them is real, and not measured under load anywhere in this repository.


## Caveats carried from the JSON

* Each target is a separate pytest process. Cross-target interference (module basename collisions, shared temp state) is therefore NOT measured here; a single whole-repository invocation may collect differently.
* `totals` is the sum over targets, not the number a single `pytest` prints. Root `testpaths` is ['tests', 'packages'], so verticals/*/packages/*/tests are counted here and are not counted by a bare `pytest`.
* A target that timed out contributes whatever its JUnit XML contained at the moment it was killed, which is usually nothing. Its row carries `timed_out: true` and its counts are a floor, not a measurement.
