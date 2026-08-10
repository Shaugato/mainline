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

Relations a migration referenced that no migration created, before this wave:
7 [src: evidence/producers/producer-census-before.json#before.absent_relations|len]

`tests/release/test_honesty_is_checkable.py` reads this document, extracts every number,
follows every reference, and fails the build when a number and its source disagree, when
a reference points outside `qa/` or `evidence/`, when a cited file is gone, when a number
carries no reference at all, or when a citation names an artefact family nobody declared.
It also plants one of every violation family into a synthetic document and requires the
checker to fire on each, because a lint that has never been red asserts nothing.

**One rule runs the other way, and it is the newest.** Every rule above fires when
evidence moves or vanishes. `families_landed_but_uncited` fires when evidence *appears*:
if an artefact family has a file on disk and this page mentions none of it, the build
fails. That is the failure this document actually suffered — the number below that got
worse had been true for a day before anyone printed it.

Digits inside `code spans` are **names**, not measurements: `ap-southeast-2`, `v26.2.5`,
SQLSTATE `23514`, a date like `2026-08-10`. Anything a skeptic would want to re-derive is
a bare number with a reference beside it.

These commands re-derive most of what is below:

```bash
python scripts/qa/report_test_state.py          # qa/test-state.json + docs/release/test-state.md
python scripts/proof/gate_refusal.py --dsn …    # evidence/gate-refusal/proof-<UTC>.json
trappoint migrate lint --root verticals/mainline/db/migrations   # the producer-absent rule
trappoint migrate up --dsn … --tree mainline --migrations …      # the forward-only runner
```

---

## PROVEN

### The database refuses the merge

This is the product's central claim and until `2026-08-10` nobody had put it to a database.
The artefact is [`evidence/gate-refusal/proof-20260810T054407Z.json`](../evidence/gate-refusal/proof-20260810T054407Z.json),
written by `scripts/proof/gate_refusal.py`, and reproduced by `just prove`.

| What happened | Value |
|---|---|
| Verdict | `PROVEN` |
| First refusal | SQLSTATE `23514`, constraint `gate_closed_when_issued`, source `reported` |
| Second refusal, same permit | SQLSTATE `P0001`, `mainline.fn_permit_merge_gate`, source `parsed` |
| Then, after one signed disposition | `ADMITTED`, SQLSTATE `00000`, a `merge_record` row with a server-computed clearance digest |
| Minimal unsatisfiable subset, cardinality | 1 [src: evidence/gate-refusal/proof-20260810T054407Z.json#refusal.refusal_ledger.mus_cardinality] |
| `gc.ttlseconds` on the cluster, pinned to the Cloud value | 4500 [src: evidence/gate-refusal/proof-20260810T054407Z.json#cluster.zone.gc_ttlseconds] |
| Migration files the run applied first | 271 [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.applied_count] |
| Migration files that failed | 0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.failed_count] |

Caveats the artefact carries: 0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#caveats|len].
That field used to hold two, and the next section is about the second of them.

The second refusal is the one to read twice. The projected counter was forced to zero out
of band — the exact attack a "materialised conflict" design has to survive — and the gate
refused anyway, because `mainline.fn_permit_merge_gate` re-derives the obligation count
instead of trusting the column it is handed. **P2 projections are enforced, never
trusted.** The third line matters just as much: a gate that always refuses is broken, not
safe, so the same history is admitted once a disposition is signed.

### The trigger projected the counter. The script did not.

**This paragraph used to be an apology.** For as long as `mainline_ops.outbox` had no
producer migration, `0121_trg_check_materialised.sql` could not apply, so the gate's own
projection trigger was absent from the applied schema — and `scripts/proof/gate_refusal.py`
wrote `mainline.permit.open_blocking` itself, to the value the gate independently
re-derives, and said so in a `caveats` block. The refusal was the database's. The counter
that provoked it was not. That earlier state is preserved verbatim in
[`evidence/gate-refusal/proof-20260810T004200Z.json`](../evidence/gate-refusal/proof-20260810T004200Z.json)
and this page keeps it visible, because a document whose credibility rests on showing its
own movement may not quietly delete where it moved from.

The producer landed. The trigger is welded. The claim is now the stronger one, and every
clause of it is a value in the evidence file rather than a sentence in this one: **the
trigger projected the counter, emitted the CDC signal, bumped the epoch, and then the gate
refused.**

| One `INSERT INTO mainline.blocking_check`, nothing else between the readings | |
|---|---|
| `mainline.permit.open_blocking` before | 0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.open_blocking.before] |
| `mainline.permit.open_blocking` after | 1 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.open_blocking.after] |
| `gate_epoch` before | 0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.gate_epoch.before] |
| `gate_epoch` after | 1 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.gate_epoch.after] |
| `check_opened` rows the trigger emitted into `mainline_ops.outbox` for that check | 1 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.outbox.rows_for_this_check] |
| Severity the proof script supplied on the check row | 0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.severity.supplied_by_this_script] |
| Severity the trigger projected onto it from the clause | 4 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.severity.projected_onto_the_check] |

Assertions in that projection block, every one of them holding:
10 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.assertions|len].

`history.open_blocking_counter_written_by` now reads
`trigger check_materialised -> mainline.fn_check_materialised`, which is the sentence the
whole repair existed to make true. Read the severity pair before anything else: the script
supplied nothing, and the database put a `blood_major` severity on the check by itself.
A counter a client writes is a client's opinion. A counter a trigger writes, on a row the
client did not touch, is the database's.

### The chain: three different numbers, and they are not interchangeable

This section used to print one figure — **applied 246 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.applied_count], failed 15 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.failed_count], of 261 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.files]** — as though it
described a deployment. It did not. It described a *census*: an applier that runs every
file and continues past each failure, so that the count at the end is a survey of the
whole stream rather than the point at which a real deployment would have stopped.

That is still the number the committed gate proof carries, and it is still true of what
that run measured:

| The proof run's own chain census, before this wave | |
|---|---|
| Migration files in the tree | 261 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.files] |
| Applied, continuing past every failure | 246 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.applied_count] |
| Failed, every one `42P01` | 15 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.failed_count] |

Failures that run could not attribute to a named, known gap:
0 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.failures_unexplained|len].

**The deployment runner tells a worse story, and this page has never printed it.**
`trappoint migrate up` is forward-only: it halts on the first refusal, which is correct
for a deployment and useless for a survey. Against that tree it halted at
`0121_trg_check_materialised` with `[42P01] relation "mainline_ops.outbox" does not
exist`, left the version DIRTY, and every file below the halt was never executed by the
runner a deployment uses at all. The census had been quietly answering a question nobody
asked.

**No artefact under `qa/` or `evidence/` records that halt, or the completed forward-only
run that has since replaced it, so this page prints no figure for either.** Both
transcripts — the halt, and a run driven today that applied the whole tree with nothing
left dirty — are in [`docs/STATE-OF-THE-BUILD.md`](STATE-OF-THE-BUILD.md), which is a
prose document and not a source a number may be drawn from here. The deployment number is
therefore *unrecorded in both directions*, and that absence is listed under NOT YET BUILT
rather than rounded away. It is the sharpest thing this page can say about its own
evidence: the measurement everyone quotes is not the measurement a deployment performs.

**What is recorded, after the seven missing producers landed.** Three independent appliers
have since run the whole tree, on two clusters, and all three report zero failures. Every
one of them is still a continue-on-error census — but a census with nothing to continue
past reaches the same end state a forward-only run would, on the DDL. It does *not* reach
the same state on the bookkeeping: attestation rows, the schema lock and the `GRANTS.yaml`
assertion are the runner's work, not the census's.

The gate proof applies the chain itself before it seeds any history, so its own count is
the third reading and the one taken most recently:
271 [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.files] files,
0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.failed_count] failures, in
63.094 [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.seconds] seconds.

| The whole tree, local node, `v26.2.5` | |
|---|---|
| Migration files executed | 271 [src: evidence/deploy/chain-261.json#files] |
| Applied | 271 [src: evidence/deploy/chain-261.json#applied] |
| Failed | 0 [src: evidence/deploy/chain-261.json#failed] |
| Wall clock, seconds | 46.35 [src: evidence/deploy/chain-261.json#wall_clock_seconds] |
| Base tables in the resulting schema | 86 [src: evidence/deploy/chain-261.json#schema_totals.base_tables] |
| Views in the resulting schema | 20 [src: evidence/deploy/chain-261.json#schema_totals.views] |

| The same tree, CockroachDB Cloud, Basic tier, `aws-ap-southeast-1` | |
|---|---|
| Migration files executed | 271 [src: evidence/deploy/cloud-chain.json#files] |
| Applied | 271 [src: evidence/deploy/cloud-chain.json#applied] |
| Failed | 0 [src: evidence/deploy/cloud-chain.json#failed] |
| Seconds for the chain | 359.1 [src: evidence/deploy/cloud-chain.json#chain_seconds] |
| Files that needed a `40001` retry | 0 [src: evidence/deploy/cloud-chain.json#files_that_needed_a_retry] |
| Connections dropped and re-established | 0 [src: evidence/deploy/cloud-chain.json#connection_reconnects] |
| `gc.ttlseconds` the cluster accepted | 4500 [src: evidence/deploy/cloud-chain.json#zone.observed] |

The Cloud chain took roughly eight times the wall clock of the local one for the same
files. That ratio is the most useful thing on this page for anyone budgeting a deployment,
and it is measured, not modelled.

**Read the movement in both directions.** The census rose from
246 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.applied_count] applied to
271 [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.applied_count], which is
the good news and the easy news. The other movement is that this page discovered it had
been quoting a survey where a reader would reasonably have heard a deployment, and the
deployment figure was *lower, and unrecorded, and is unrecorded still* — including now
that a forward-only run has been driven successfully. Which of those two a reader takes
away is the test of whether this page is doing its job.

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

**This census predates the seven producer migrations and has not been retaken.** It was
measured against a tree in which those files did not exist, so every row above is a
statement about that tree, not about the one in the working directory. Retaking it is
cheap and nobody has done it; until they do, reading these counts as current is the
reader's error and this sentence is here to prevent it.

Three further things about this table are worth saying out loud rather than leaving for a
reader to notice.

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

**And the ratchet is red today, on a wave whose total went down.** `scripts/qa/ruff_ratchet.py`
refuses the working tree. The findings total is now *below* the frozen
847 [src: qa/ruff-ratchet.json#lint.total], and the unformatted-file count is *above* the
frozen 245 [src: qa/ruff-ratchet.json#format.unformatted_files]. The ratchet gates per rule
and per tree rather than on a headline sum, so a change that removes findings in one
directory and adds five hard-gate violations — rules whose baseline is zero — in another
cannot buy its way past it with the total. Every regression is in `scripts/`, where this
wave's new scripts landed, and in `verticals/`, where its migrations did. The exact
per-rule output is in [`docs/STATE-OF-THE-BUILD.md`](STATE-OF-THE-BUILD.md); no committed
artefact holds the *measured* figures, because re-baselining is how a ratchet is defeated
and nobody in this wave owned that file. **Discovered, not fixed.**

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

### Seven tables had no migration at all — and two of them were invisible to the census

Their consumers were written — triggers, views, RLS policies — and their producer never
was. This page said **five** for as long as it had only a SQLSTATE census to go on. The
true count is seven, and *why the census said five* is worth more than the fix.

**CockroachDB names only the first absent relation in a statement.** Both views that read
`mainline_meas.standing` also `JOIN` `mainline_meas.person_measure_policy`, and `standing`
is named first in each, so the second relation never appeared in an error string —
anywhere, ever. A census built by classifying SQLSTATEs could not have found it. The
seventh, `mainline_ops.site_register_signal`, blocked no migration at all: it is named by
the RLS matrix and by a negative assertion that no row-level security exists on it, so a
chain census had nothing to trip over either.

The gate proof's SQLSTATE census counted 5 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.unproduced_tables_enumerated|len] and the producer-absent lint, which differences every schema-qualified relation a migration references against every relation the tree creates, counted 7 [src: evidence/producers/producer-census-before.json#before.absent_relations|len].

That is not two opinions. It is one instrument reading through a keyhole and another
reading the source. The lesson is the general one and it outlives this repair: **a defect
census built from error messages measures what the error messages can express.**

The observed red, in full, is
[`evidence/producers/producer-census-before.json`](../evidence/producers/producer-census-before.json),
taken over the tree at the commit before any producer landed:

| The producer-absent rule, before | |
|---|---|
| Migration files checked | 261 [src: evidence/producers/producer-census-before.json#cli_transcript.before.files_checked] |
| Findings, all of them `producer-absent` | 7 [src: evidence/producers/producer-census-before.json#cli_transcript.before.findings] |
| Schema-qualified relations the tree creates | 134 [src: evidence/producers/producer-census-before.json#before.produced] |
| Schema-qualified relation references it resolves | 586 [src: evidence/producers/producer-census-before.json#before.references] |

The seven, each named by the consumers that were written before it:

* `mainline_ops.outbox`
* `mainline.identity_assignment`
* `mainline.patrol_run`
* `mainline_meas.agent_action`
* `mainline_meas.standing`
* `mainline_meas.person_measure_policy` — shadowed behind `standing` in both views that read it
* `mainline_ops.site_register_signal` — blocked a negative RLS assertion, never a migration

Migrations that failed solely because one of them was missing:
15 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.failures_attributable_to_an_unproduced_table|len] —
`0121_trg_check_materialised`, `0145a_trg_cbm_account_guard`, `0163_v_fixity_coverage`,
`0164_v_agent_actions`, `0165_v_gate_latency_daily`, `0166_v_txn_restart_daily`,
`0171_v_standing_components`, `0172_v_my_record`, `0187_standing_rls_enable`,
`0187a_standing_rls_force`, `0187b_policy_standing_blind`,
`0187c_policy_standing_assay_read`, `0187d_policy_standing_assay_insert`,
`0187e_policy_standing_view_owner_read`, `0198x_no_rls_on_cdc_sources`.
Each is recorded in the gate-refusal evidence file with its own `42P01` and the table it
wanted.

**The paired green, from the same rule and the same command:**

| The producer-absent rule, after | |
|---|---|
| Migration files checked | 271 [src: evidence/producers/producer-census-before.json#cli_transcript.after.files_checked] |
| Findings | 0 [src: evidence/producers/producer-census-before.json#cli_transcript.after.findings] |
| Schema-qualified relations the tree creates | 141 [src: evidence/producers/producer-census-before.json#working_tree_at_capture.produced] |
| Schema-qualified relation references it resolves | 603 [src: evidence/producers/producer-census-before.json#working_tree_at_capture.references] |

Relations the tree references with no producer, after:
0 [src: evidence/producers/producer-census-before.json#working_tree_at_capture.absent_relations|len].

The rule that found them is now part of the migration lint, so the eighth instance of this
defect class fails at lint time rather than at deployment time. That is the durable half
of this repair; the seven files are the perishable half.

### The forward-only deployment runner has been driven, and wrote no artefact

Every number this page prints about the chain comes from a continue-on-error applier. The
runner a deployment uses — `trappoint migrate up`, forward-only, halting on the first
refusal, writing an attestation row per file — **has now been driven over the whole tree
and completed**, with nothing left dirty and an attestation head whose ordinal equals the
file count. The bookkeeping half is no longer untested.

**It still wrote no artefact under `qa/` or `evidence/`, so this page prints no figure for
it.** `evidence/chain/` exists and holds a README and no run. The full transcript —
command, the runner's own output, the `schema_migration` state, the attestation count and
the `migrate attest` verdict — is in
[`docs/STATE-OF-THE-BUILD.md`](STATE-OF-THE-BUILD.md), which is a prose document and not a
source a number may be drawn from here.

That is a deliberately awkward position to leave a document in, and it is the correct one.
The rule that makes this page worth reading is that a quantity resolves to a machine-readable
file; suspending it for a good result would be exactly the move it exists to prevent. **A
measurement I cannot cite is a measurement this page does not print, even when it is the
best news in the wave.**

> **When it does exist, this page breaks on purpose.** `evidence/chain/` is a declared
> reference family in `tests/release/test_honesty_is_checkable.py`, and the moment a
> `chain-<UTC>.json` appears there, `test_the_document_does_not_lag_a_family_that_landed`
> fails and names it. The fix is to rewrite this section around the artefact's
> `result.applied`, `result.failed`, `result.dirty` and `result.complete`. A red build is
> the correct response to evidence arriving that the prose has not absorbed.

### The conformance suite has still not been demonstrated

With no database, the suite skips: 183 [src: qa/test-state.json#packages.packages/trappoint-conformance.runs.none.skipped].
With a database present but **unmigrated**, it does not skip — it errors:
182 [src: qa/test-state.json#packages.packages/trappoint-conformance.runs.cluster.errored].
The cause was a `SetupRefused` from `cases/_world.py` — *"building the LEGAL world failed
at 'site' … relation `trappoint_ref.site` does not exist"* — which is the suite correctly
refusing to call an unbuilt world a refusal.

**The four defects that made a census impossible have since been repaired in the package**
and none of them was a design fault: the CLI now loads the corpus, `cases/` is inside the
wheel, the runner catches `SetupRefused` so one unbuildable world reports one result
instead of aborting the run, and the world builder writes the columns `mainline.site`
actually declares. A capability probe now resolves each case's `requires` token against
the live catalogue instead of waiting for a human to pass a flag.

**And no census has been taken.** `qa/conformance-census.json` does not exist. Nobody has
run the repaired suite to completion against a migrated cluster and published pass, fail
and cannot-run per case with the missing object named for every cannot-run. Until that
file exists, the conformance case list is a *plan* with a working runner attached, which
is better than a plan and is not a result. **This remains the single largest gap between
what this repository contains and what it has shown.**

Six of the capability tokens name relations this repository has deliberately not authored
— `propagation`, `observed_assertion`, `merge_conflict`, `frontier_move`,
`discordance_warrant`, `coverage_certificate`. Those cases cannot pass and are expected to
report cannot-run with the object named. A demonstrated suite at a modest pass rate is a
categorically different artefact from an undemonstrated one; this repository still has the
second kind.

> **Same deliberate breakage as above.** `qa/conformance-census.json` is a declared
> reference family. The moment it exists, the checker fails until this section is replaced
> by its per-status totals with a named reason on every cannot-run.

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
**`qa/reuse-ratchet.json` is not.** Licence-header compliance is therefore an *uncounted*
number in this document. The quality lead's own census found thousands of files carrying
neither an SPDX header nor a `.license` sidecar, and two spellings in use for the same
forked identifier — `FSL-1.1-ALv2`, which is not an SPDX-registered id, against the
`LicenseRef-` form REUSE requires. `REUSE.toml` now exists and `LICENSES/` now holds four
licence texts, which is progress and is not a count. No committed artefact re-derives the
header census, so this page refuses to print a figure for it.

Worse, and unchanged: `.github/workflows/ci.yml` has a `checkers` job that asserts five
named programs exist, **`scripts/qa/check_reuse.py` is not one of the files on disk**, and
every substantive job declares `needs: [checkers]`. The pipeline still cannot start, so
every CI number in this repository is a number about a lane that has not run.

### Other things this document will not pretend about

* **Nothing has ever run against CockroachDB Cloud in CI.** The nightly truth check is
  designed, not scheduled. The migration chain *has* now been applied to the Cloud cluster
  by hand — the table in PROVEN is that run — and a hand-run is not a lane.
* **The console lane exists and has not been observed running.** A workflow for
  `verticals/mainline/apps/console` was added on `2026-08-10`. Before that date a console
  of several hundred TypeScript files carried a complete `pnpm run ci` — eslint at
  `--max-warnings 0`, `tsc` twice, `vitest run`, a production build, a bundle budget — and
  not one of those had ever run in CI. `pnpm run ci` was measured on a developer machine
  before the workflow was committed. No GitHub Actions run of it is recorded here, and
  while the `checkers` job above fails, no lane runs. This page prints no file count
  because no committed artefact takes one.
* **`uv` is not installed on this machine.** Every command quoted in this repository's
  documentation was run with the virtual environment's interpreter directly. That
  substitution changes nothing about what the database did and everything about whether a
  stranger following the README gets the same result.
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

The one cross-region cost that *is* measured is DDL, not recall: the migration chain took
359.1 [src: evidence/deploy/cloud-chain.json#chain_seconds] seconds against the Singapore
cluster and 46.35 [src: evidence/deploy/chain-261.json#wall_clock_seconds] seconds against
the local node, for the same files. Read that as an order-of-magnitude warning about the
hop, not as a recall figure, because it is not one.

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
  Cloud value, 4500 [src: evidence/gate-refusal/proof-20260810T004200Z.json#cluster.zone.gc_ttlseconds]
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
* Run `trappoint migrate lint --root verticals/mainline/db/migrations`. A
  `producer-absent` finding means a relation has consumers and no producer again, and the
  forward-only chain will halt on it.
* Drive `trappoint migrate up` from a fresh database and write down where it stops. If it
  stops anywhere, the tables above are describing a survey and not a deployment.
* Run `trappoint-verify verify --bundle evidence/reference-ledger/bundle.json`. If it
  exits `0` rather than `2`, the cryptographic checks have landed and this page is stale.
* Open `docs/release/test-state.md` and read the skip reasons. Every one of them is a
  sentence some fixture author wrote about a thing that is missing.

**One recursion, stated rather than hidden.** This document is checked by a test that the
census counts. The census row for `tests/release` was taken at a moment when this file was
in a particular state; running the suite again necessarily changes that row. The document
does not chase its own tail — the totals above are the ones in the committed JSON, and the
committed JSON is what the checker compares against.
