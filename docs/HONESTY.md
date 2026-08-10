<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# HONESTY

This is not a disclaimer. A disclaimer is prose nobody can falsify, and this project's
whole pitch is that it refuses to overclaim — which is worth exactly as much as the
mechanism that would catch it lying.

So: **every quantity on this page carries an inline reference to the file that produced
it**, like this — 

Migration files in the chain: 261 [src: evidence/gate-refusal/proof-20260809T213857Z.json#chain.files]

`tests/release/test_honesty_is_checkable.py` reads this document, extracts every number,
follows every reference, and fails the build when a number and its source disagree, when
a reference points outside `qa/` or `evidence/`, when a cited file is gone, or when a
number carries no reference at all. It also plants one of every violation family into a
synthetic document and requires the checker to fire on each, because a lint that has
never been red asserts nothing.

Digits inside `code spans` are **names**, not measurements: `ap-southeast-2`, `v26.2.5`,
SQLSTATE `23514`, a date like `2026-08-10`. Anything a skeptic would want to re-derive is
a bare number with a reference beside it.

Two commands re-derive nearly everything below:

```bash
python scripts/qa/report_test_state.py          # qa/test-state.json + docs/release/test-state.md
python scripts/proof/gate_refusal.py --dsn …    # evidence/gate-refusal/proof-<UTC>.json
```

---

## PROVEN

### The database refuses the merge

This is the product's central claim and until `2026-08-10` nobody had put it to a database.
The artefact is [`evidence/gate-refusal/proof-20260809T213857Z.json`](../evidence/gate-refusal/proof-20260809T213857Z.json),
written by `scripts/proof/gate_refusal.py`, and reproduced by `just prove`.

| What happened | Value |
|---|---|
| Verdict | `PROVEN` |
| First refusal | SQLSTATE `23514`, constraint `gate_closed_when_issued`, source `reported` |
| Second refusal, same permit | SQLSTATE `P0001`, `mainline.fn_permit_merge_gate`, source `parsed` |
| Then, after one signed disposition | `ADMITTED`, SQLSTATE `00000`, a `merge_record` row with a server-computed clearance digest |
| Minimal unsatisfiable subset, cardinality | 1 [src: evidence/gate-refusal/proof-20260809T213857Z.json#refusal.refusal_ledger.mus_cardinality] |
| `gc.ttlseconds` on the cluster, pinned to the Cloud value | 4500 [src: evidence/gate-refusal/proof-20260809T213857Z.json#cluster.zone.gc_ttlseconds] |

The second refusal is the one to read twice. The projected counter was forced to zero out
of band — the exact attack a "materialised conflict" design has to survive — and the gate
refused anyway, because `mainline.fn_permit_merge_gate` re-derives the obligation count
instead of trusting the column it is handed. **P2 projections are enforced, never
trusted.** The third line matters just as much: a gate that always refuses is broken, not
safe, so the same history is admitted once a disposition is signed.

**What the proof does not settle.** The migration chain did not fully apply.

| | |
|---|---|
| Migration files in the tree | 261 [src: evidence/gate-refusal/proof-20260809T213857Z.json#chain.files] |
| Applied | 246 [src: evidence/gate-refusal/proof-20260809T213857Z.json#chain.applied_count] |
| Failed | 15 [src: evidence/gate-refusal/proof-20260809T213857Z.json#chain.failed_count] |

Every failure is enumerated in the evidence file with its SQLSTATE and the object it
wanted, and the number the run could **not** attribute to a known, named gap is
0 [src: evidence/gate-refusal/proof-20260809T213857Z.json#chain.failures_unexplained|len].
The gate's own projection trigger, `0121_trg_check_materialised.sql`, is among the
casualties — so the proof script wrote `mainline.permit.open_blocking` itself, to the
value the gate independently re-derives, and says so in its own `caveats` block. The
refusal is still the database's. The counter that provoked it, on that run, was not.

### The offline custody bundle

`trappoint-verify` over the committed reference ledger is the Tier-1 verification in
`VERIFY.md`: no credential, no network, no cluster. The census runs it and records its
own JSON verdict.

| | |
|---|---|
| Checks that ran and held | 9 [src: qa/test-state.json#external_checks.custody_bundle_verification.counts.passed] |
| Checks that failed | 0 [src: qa/test-state.json#external_checks.custody_bundle_verification.counts.failed] |
| Checks that **did not run at all** | 7 [src: qa/test-state.json#external_checks.custody_bundle_verification.counts.not_checked] |
| Checks in the suite | 16 [src: qa/test-state.json#external_checks.custody_bundle_verification.counts.total] |
| Exit code | 2 [src: qa/test-state.json#external_checks.custody_bundle_verification.exit_code] |

Exit `2` is the tool telling the truth about itself: *everything that ran held, and this
is NOT a clean verification.* The seven that did not run are the cryptographic half —
log signature, RFC-3161 bracket, beacon, witness quorum, S3 object-lock, gate
self-attestation, WebAuthn re-verification. They are registered, named, and report what
they *would* have proved. **Do not read the nine passes as a verified ledger.** What is
verified is the Merkle structure: leaf recomputation, inclusion, consistency across every
consecutive checkpoint pair, link-chain density from a zero genesis, canonicaliser
identity, receipt coverage and bundle totality.

### The test census

Taken by `scripts/qa/report_test_state.py`, one pytest subprocess per distribution and per
test root, twice: once with `--crdb=none` (no database may be obtained, so every
cluster-backed test skips with the reason its own fixture wrote) and once with
`--crdb=reuse` against one shared node. Full document:
[`docs/release/test-state.md`](release/test-state.md).

| | no cluster | one shared cluster |
|---|---|---|
| targets | 26 [src: qa/test-state.json#totals.none.targets] | 26 [src: qa/test-state.json#totals.cluster.targets] |
| tests | 8845 [src: qa/test-state.json#totals.none.tests] | 7187 [src: qa/test-state.json#totals.cluster.tests] |
| passed | 8065 [src: qa/test-state.json#totals.none.passed] | 6960 [src: qa/test-state.json#totals.cluster.passed] |
| failed | 44 [src: qa/test-state.json#totals.none.failed] | 29 [src: qa/test-state.json#totals.cluster.failed] |
| errored | 0 [src: qa/test-state.json#totals.none.errored] | 182 [src: qa/test-state.json#totals.cluster.errored] |
| skipped | 736 [src: qa/test-state.json#totals.none.skipped] | 16 [src: qa/test-state.json#totals.cluster.skipped] |
| targets that timed out | 0 [src: qa/test-state.json#totals.none.timed_out_targets] | 1 [src: qa/test-state.json#totals.cluster.timed_out_targets] |

Distinct skip reason strings, no-cluster pass: 43 [src: qa/test-state.json#skip_reasons.none|len].
Every one of them is printed verbatim, with its count, in
[`docs/release/test-state.md`](release/test-state.md). A skip with no reason is
indistinguishable from a test that was quietly deleted, so the census refuses to record
one.

Three things about this table are worth saying out loud rather than leaving for a reader
to notice.

* **It is a sum over subprocesses, not what one `pytest` prints.** Each target runs alone,
  so cross-target interference is not measured here.
* **The cluster pass has more errors than the no-cluster pass, not fewer.** That is not a
  paradox; it is `packages/trappoint-conformance`, and it is in NOT YET BUILT below.
* **Some of those failures are deliberate.** Tests carrying `pl2_red` or `g4alpha` in
  their names are written to be red until the thing they describe exists. PL-2: a suite
  that has never been red asserts nothing. They are published rather than deleted.

### Lint and types are counted, not claimed

Nothing here is "clean". The numbers are frozen, published, and may fall but not rise.

| | |
|---|---|
| `ruff check .` findings | 847 [src: qa/ruff-ratchet.json#lint.total] |
| Files `ruff format` would rewrite | 245 [src: qa/ruff-ratchet.json#format.unformatted_files] |
| `mypy` errors across the workspace | 12 [src: qa/mypy-ratchet.json#total_errors] |
| Source files mypy actually checked | 477 [src: qa/mypy-ratchet.json#source_files_checked] |

A truthful large number that cannot grow beats a fabricated zero. `qa/README.md` gives the
one command that re-derives each of them.

**And the mypy pair is already one distribution stale.** The ratchet records
29 [src: qa/mypy-ratchet.json#distributions|len] distributions; the workspace has since
gained one more — `mainline-corpus`, which had source on disk and no `pyproject.toml` until
this wave — and `mypy.ini` has no section for it. Two tests under `tests/release/` are red
about exactly that, by name, right now. The correct reading of the two mypy rows above is
*"what the checker said about the distributions it was pointed at"*, not *"what the
workspace type-checks like"*.

---

## SYNTHETIC

Everything in this section is real code operating on **manufactured inputs**. None of it
is a claim about a real operator's data, and none of it should be read as one.

* **The corpus is authored.** The procedures, clauses, setpoints, incidents and permits
  under `verticals/mainline/` were written for this repository. The compressor-setpoint
  story on the front page is a *designed* worked example, not an extract from anyone's
  document management system. No real incident, no real fatality, no real site.
* **The model transcripts are recorded cassettes.** Agent tests replay captured
  request/response pairs. A green agent test proves the code handles that recorded
  exchange; it does not prove anything about a live model's behaviour today. Where a live
  call is genuinely required the test **skips with a reason** and the reason is in the
  census.
* **The reference-ledger keys are named `NOT-SECRET` because they are.** Every file under
  `evidence/reference-ledger/keys/` is a published private key committed on purpose, so a
  stranger can verify the bundle offline without asking anyone for anything. They are
  worthless, and they must never be reused for anything that matters.
* **The signed reference ledger is a fixture.** It is internally consistent and its
  structure verifies — see the custody table above — but it was generated by
  `evidence/reference-ledger/generate.py`, not accumulated by a system in production.
* **The AWS evidence store is described, not exercised under load.** The archive section
  of the bundle carries object-lock modes and retention dates; the check that would
  compare them against live object versions is one of the seven that did not run.

---

## NOT YET BUILT

### Five tables have no migration at all

Their consumers were written — triggers, views, RLS policies — and their producer never
was. Count of tables with no producer:
5 [src: evidence/gate-refusal/proof-20260809T213857Z.json#chain.unproduced_tables_enumerated|len]

* `mainline_ops.outbox`
* `mainline.identity_assignment`
* `mainline.patrol_run`
* `mainline_meas.agent_action`
* `mainline_meas.standing`

Migrations that fail solely because one of those five is missing:
15 [src: evidence/gate-refusal/proof-20260809T213857Z.json#chain.failures_attributable_to_an_unproduced_table|len] —
`0121_trg_check_materialised`, `0145a_trg_cbm_account_guard`, `0163_v_fixity_coverage`,
`0164_v_agent_actions`, `0165_v_gate_latency_daily`, `0166_v_txn_restart_daily`,
`0171_v_standing_components`, `0172_v_my_record`, `0187_standing_rls_enable`,
`0187a_standing_rls_force`, `0187b_policy_standing_blind`,
`0187c_policy_standing_assay_read`, `0187d_policy_standing_assay_insert`,
`0187e_policy_standing_view_owner_read`, `0198x_no_rls_on_cdc_sources`.
Each is recorded in the evidence file with its own `42P01` and the table it wanted.

They are not invented in passing. A new table takes a number the
`migrations.allocation.toml` band grants to a named owner, and no worker in this wave owns
those bands, so the gap is **recorded** rather than papered over. The most consequential
one is `mainline_ops.outbox`: without it the gate's projection trigger cannot be
installed, which is why the proof run had to write `open_blocking` itself.

### The conformance suite has not been demonstrated

With no database, the suite skips: 183 [src: qa/test-state.json#packages.packages/trappoint-conformance.runs.none.skipped].
With a database present but **unmigrated**, it does not skip — it errors:
182 [src: qa/test-state.json#packages.packages/trappoint-conformance.runs.cluster.errored].
The cause is a `SetupRefused` from `cases/_world.py` — *"building the LEGAL world failed
at 'site' … relation `trappoint_ref.site` does not exist"* — which is the suite correctly
refusing to call an unbuilt world a refusal.

**So: this census demonstrates no conformance case.** The case bodies exist, the manifest
enumerates them, `just migrate && just conform` is the invocation that would run them, and
the census's shared node is deliberately bare. Until a census is taken against a migrated
cluster, the conformance case list is a *plan*, not a result. That is the single largest
gap between what this repository contains and what it has shown.

### One target could not be measured at all

`tests/integration` under the cluster pass hit the census's own wall-clock ceiling. Its
counts in the JSON are a floor, not a measurement, and the row carries `timed_out: true`.
Targets in that state, cluster pass: 1 [src: qa/test-state.json#totals.cluster.timed_out_targets].
It was re-run with the ceiling raised to 2400 [src: qa/test-state.json#merges.0.per_target_timeout_seconds]
seconds and **still did not finish**, so the number of integration tests that pass against
a live database is, today, unknown. Without a database the same target reports its counts
in about a minute, which is the shape of a suite whose cluster path is doing far more work
than anyone has budgeted for.

### Ratchets that do not exist yet

`qa/ruff-ratchet.json` and `qa/mypy-ratchet.json` are on disk and quoted above.
**`qa/reuse-ratchet.json` is not, and `REUSE.toml` does not exist either.** Licence-header
compliance is therefore an *uncounted* number in this document. The quality lead's own
census found thousands of files carrying neither an SPDX header nor a `.license` sidecar,
and two spellings in use for the same forked identifier — `FSL-1.1-ALv2`, which is not an
SPDX-registered id, against the `LicenseRef-` form REUSE requires. `LICENSES/` now holds
the two licence texts, which is progress and is not a count. No committed artefact
re-derives the header census, so this page refuses to print a figure for it. When the
ratchet lands, its numbers belong here with a reference like every other number.

### Other things this document will not pretend about

* **Nothing has ever run against CockroachDB Cloud in CI.** The nightly truth check is
  designed, not scheduled.
* **The console has had no CI.** A complete `pnpm run ci` exists in
  `verticals/mainline/apps/console`; nothing invoked it.
* **The evidence SBOM path is gated on but absent.** One census skip says so in its own
  words: no kernel-image SBOM is committed, "so the image contents are unproven. NOT A
  PASS."

---

## GEOGRAPHY AND LATENCY

**Inference is in Australia. The database is in Singapore. There is no end-to-end
Australian data residency, and any claim of it would be false.**

| | |
|---|---|
| Bedrock inference | `ap-southeast-2` (Sydney), `au.*` Claude inference profiles |
| CockroachDB Cloud cluster | `aws-ap-southeast-1` (Singapore), Basic tier |
| Why they are apart | `ap-southeast-2` is Advanced-tier only on CockroachDB Cloud — absent from the Basic and Standard region lists |
| Bedrock Rerank in `ap-southeast-2` | **not available.** No dependency was taken on it |
| The cross-region hop | real, and **unmeasured under load** anywhere in this repository |

The recall path therefore crosses a region boundary on every embedding call, and this
repository contains no p50, no p99 and no load profile for that hop. Anyone who tells you
what MAINLINE's recall latency is in production is guessing.

### Every timing in the demo is a LOCAL timing

The inner loop is a local single-node CockroachDB in Docker, and it is not close.

| | |
|---|---|
| Local benchmark: rows inserted | 5000 [src: qa/test-state.json#platform.local_benchmark.rows] |
| Local benchmark: `VECTOR` dimensions | 256 [src: qa/test-state.json#platform.local_benchmark.dimensions] |
| Local: seconds for schema plus vector index | 5.3 [src: qa/test-state.json#platform.local_benchmark.ddl_seconds] |
| Local: seconds for the inserts | 6.5 [src: qa/test-state.json#platform.local_benchmark.insert_seconds] |
| Local: seconds, whole shape | 11.8 [src: qa/test-state.json#platform.local_benchmark.seconds] |
| Cloud Basic, nine DDL statements, seconds | 120 [src: qa/test-state.json#platform.cloud_basic_comparison.seconds] |

**Two things about that table are corrections, not decoration.**

The Cloud figure is a **floor**: the observation was recorded as *greater than* that
number, not equal to it, and it was **not re-measured by this census**, which holds no
Cloud credential and takes none. It is transcribed, and the JSON says so in the same
object — `measured_here: false` — with the file it came from.

The local figure is **not** the one quoted elsewhere in this repository. The kernel lead
recorded a comparable local shape at 2.4 [src: qa/test-state.json#platform.kernel_lead_local_reference.seconds]
seconds; the census measures its own shape at the number in the table, because it also
builds a vector index before inserting and neither run recorded the other's dimensionality
or batch size. They are the same order of magnitude and they are not the same
measurement, so this page quotes the one it took. An earlier draft of the same benchmark
used `executemany` and spent about twice as long on the inserts alone — five thousand
round trips against ten — which is a fact about the driver, not about the database, and is
why the committed benchmark batches. The exact pair of readings is in the comment beside
the code that took them.

Consequences a viewer of the demo should hold on to:

* A stopwatch on the demo is measuring Docker on a laptop, not a managed cluster across a
  region boundary.
* Local `gc.ttlseconds` is the **more permissive** of the two, and the two artefacts on
  this page disagree about it on purpose. The gate-refusal run pinned its cluster to the
  Cloud value, 4500 [src: evidence/gate-refusal/proof-20260809T213857Z.json#cluster.zone.gc_ttlseconds]
  seconds; the census probed the same node and read
  14400 [src: qa/test-state.json#cluster.gc_ttlseconds], the local default, because a
  census does not reconfigure the machine it is measuring. `just up` performs the
  alignment, precisely so a time-travel assumption cannot pass here and fail on Cloud.
* Prefix-constrained ANN uses the vector index only when the index is **named in the
  query**; at demo corpus scale a cost-based optimizer legitimately prefers a scan. The
  arms pin the index rather than hoping.

---

## How to falsify this page

* Re-run `python scripts/qa/report_test_state.py` and diff `qa/test-state.json`. If a
  number here no longer matches, `pytest tests/release/test_honesty_is_checkable.py`
  fails and names both values.
* Re-run `just prove`. A different SQLSTATE, a different constraint name, or an
  `admission` that does not admit is a falsification of the central claim, and the
  evidence file will say so with `verdict: NOT PROVEN`.
* Run `trappoint-verify verify --bundle evidence/reference-ledger/bundle.json`. If it
  exits `0` rather than `2`, the cryptographic checks have landed and this page is stale.
* Open `docs/release/test-state.md` and read the skip reasons. Every one of them is a
  sentence some fixture author wrote about a thing that is missing.

**One recursion, stated rather than hidden.** This document is checked by a test that the
census counts. The census row for `tests/release` was taken at a moment when this file was
in a particular state; running the suite again necessarily changes that row. The document
does not chase its own tail — the totals above are the ones in the committed JSON, and the
committed JSON is what the checker compares against.
