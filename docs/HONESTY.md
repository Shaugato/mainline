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

**That sentence used to continue: "no artefact under `qa/` or `evidence/` records that
halt, or the completed forward-only run that has since replaced it, so this page prints
no figure for either." It is no longer true, and this is the correction.** The artefact
landed as
[`evidence/chain/chain-20260810T062542Z.json`](../evidence/chain/chain-20260810T062542Z.json),
written by `scripts/chain/apply_chain.py` against a database the run created for itself.
The paragraph is kept rather than replaced because the shape of the admission is the
point: this page said the number was unrecorded for as long as it was, and printed it the
day it was not.

The halt itself remains unrecorded in a citable artefact, and the numbers below are the
*completed* run only. The earlier transcript is in
[`docs/STATE-OF-THE-BUILD.md`](STATE-OF-THE-BUILD.md), which is a prose document and not a
source a number may be drawn from here.

| The runner a deployment uses: `trappoint migrate up`, forward-only, `--attest each` | |
|---|---|
| Migration files the runner was given | 271 [src: evidence/chain/chain-20260810T062542Z.json#result.files] |
| Applied, halting on the first refusal — there was none | 271 [src: evidence/chain/chain-20260810T062542Z.json#result.applied] |
| Failed | 0 [src: evidence/chain/chain-20260810T062542Z.json#result.failed] |
| Left DIRTY | `false` [src: evidence/chain/chain-20260810T062542Z.json#result.dirty] |
| A deployment of this tree would have succeeded | `true` [src: evidence/chain/chain-20260810T062542Z.json#result.complete] |
| Versions forced past a failure | 0 [src: evidence/chain/chain-20260810T062542Z.json#operation.forced_versions] |
| Schema-attestation head ordinal | 271 [src: evidence/chain/chain-20260810T062542Z.json#attestation.head.ordinal] |
| Attestation rows, genesis included | 272 [src: evidence/chain/chain-20260810T062542Z.json#attestation.rows] |
| `migrate up` alone, seconds | 1931.459 [src: evidence/chain/chain-20260810T062542Z.json#steps.1.seconds] |
| Bootstrap, runner and grants together, seconds | 2724.962 [src: evidence/chain/chain-20260810T062542Z.json#wall_clock_seconds] |

**Read the last two rows against the census.** The same
271 [src: evidence/chain/chain-20260810T062542Z.json#result.files] files take
2724.962 [src: evidence/chain/chain-20260810T062542Z.json#wall_clock_seconds] seconds
through the runner and
46.35 [src: evidence/deploy/chain-261.json#wall_clock_seconds] seconds through the
continue-on-error applier, on the same local node. Nearly all of that difference is the
`--attest each` fingerprint, recomputed twice and compared after every statement. A
deployment that wants the attestation chain pays for it, and this page would rather print
the expensive number than the flattering one.

**The bookkeeping half, which a census cannot reach at all.** The runner also asserted the
grants matrix: 112 [src: evidence/chain/chain-20260810T062542Z.json#grants.statements_asserted]
statements applied and
11 [src: evidence/chain/chain-20260810T062542Z.json#grants.statements_skipped] skipped
because the object they grant on does not exist. Those eleven are named in the artefact —
`mainline.propagation`, `mainline.merge_conflict`, `mainline.observed_assertion` and eight
more — and they are **reported, not authored**: no migration in the tree references any of
them, so none of them blocks anything. A relation that only a grant matrix names is a
smaller kind of gap than a relation a trigger reads, and the two are not summed here.

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
deployment figure was *lower, and unrecorded*. **That second half has now closed too**:
the deployment figure is
271 [src: evidence/chain/chain-20260810T062542Z.json#result.applied], recorded, and equal
to the census — which it is only because the seven producers landed. Which of those two
movements a reader takes away is still the test of whether this page is doing its job, and
the harder one to keep in view is that for a day the two numbers were different and only
one of them was printed.

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

**The table above is the committed census, and a live run on `2026-08-12` disagrees with
it — in the bad direction.** The census is what the checker for this page compares against,
so the rows stay as they are; the disagreement is printed here rather than absorbed,
because a page that only updated when the news was good would be worth nothing:

```
$ trappoint-verify verify --bundle evidence/reference-ledger/bundle.json
FAIL  check 10  canonicaliser_identity   9 canonicaliser finding(s)
      - the bundle declares canon_src_sha256 260ed37ddc61…; the canonicaliser this
        verifier is running hashes to d09036a85b02…
      - checkpoint 0: its signed `canon:` line is '1 260ed37d…', expected '1 d09036a8…'
        (and seven more checkpoints, each named)
16 checks | 8 passed | 1 failed | 7 not checked
exit 1: 1 finding(s). This bundle does not verify.
```

A check the census recorded as passing now **fails**, and it fails for the reason it exists:
the bundle carries the hash of the canonicaliser that produced it, and the canonicaliser in
the tree has moved. **That is real drift and the mechanism caught it.** Two consequences
worth stating plainly. The count of checks that *held* is one lower than the table says.
And the exit code moved from `2` to `1` — from *nothing failed and this is not clean* to
*something failed* — which is a different sentence about the same bundle. The repair is
owed by the custody domain and is recorded in `docs/CI-STATE.md`; retaking the census is
what will move the table.

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
| `ruff check .` findings | 671 [src: qa/ruff-ratchet.json#lint.total] |
| Files `ruff format` would rewrite | 0 [src: qa/ruff-ratchet.json#format.unformatted_files] |
| `mypy` errors across the workspace | 0 [src: qa/mypy-ratchet.json#total_errors] |
| Source files mypy actually checked | 660 [src: qa/mypy-ratchet.json#source_files_checked] |

Distributions that one run covered: 32 [src: qa/mypy-ratchet.json#distributions|len].

A truthful large number that cannot grow beats a fabricated zero. `qa/README.md` gives the
one command that re-derives each of them.

**The mypy zero is the one number on this page that has to defend itself, and here is the
defence.** A zero is what a checker that ran nothing also prints, so the row above is
worth nothing without the row beneath it and the count beside it: one invocation, over
every distribution the workspace publishes, and the file count is not smaller than the
`.py` files those targets hold. `tests/release/test_mypy_covers_workspace.py` asserts all
three, and it asserts them the hard way — one of its cases plants a broken plugin so mypy
dies with no completion line, and requires `--write-ratchet` to REFUSE rather than bank
`0 errors over 0 files`. Before that guard existed, a clean run recorded
`source_files_checked` as zero, because the expression that read the count matched only
mypy's failure line. The published pair would therefore have read *no type errors, in
nothing*, and nothing anywhere would have objected.

**That paragraph said the ratchet was red on a wave whose lint total had fallen while its
unformatted-file count had risen, and that no committed artefact held the measured
figures. It was true when it was written. Both halves have since moved, in the same
direction, and the artefact now holds them.** The frozen floors are
**671 [src: qa/ruff-ratchet.json#lint.total]** lint findings and
**0 [src: qa/ruff-ratchet.json#format.unformatted_files]** files the formatter would
rewrite.

**The formatter half is now met and the lint half is not, and the lane is red for the
second one.** On the runner, `ruff format --check .` rewrites nothing — that count reached
its floor and stayed there. `ruff check .`, on the same run, reports a total *above* the
frozen lint floor, so `scripts/qa/ruff_ratchet.py` refuses the tree. **That refusal is
correct and it is left standing.** Re-freezing the floor upward would silence it, which is
the one thing a ratchet exists to prevent; the numbers here are therefore the floors, not
a fresh measurement dressed as one.

The ratchet still gates per rule and per tree rather than on a headline sum, so a change
that removes findings in one directory and adds a hard-gate violation — a rule whose
baseline is zero — in another cannot buy its way past it with the total. **No baseline was
raised to absorb a regression, and none was lowered to manufacture a green:** the frozen
file records what the tree measures, which is the only move a falling ratchet permits.

What emptied the format count was files being formatted, one lane naming each of them,
not a threshold being moved.

**"And the mypy pair is already one distribution stale." That paragraph said the ratchet
recorded twenty-nine distributions, that the workspace had gained `mainline-corpus`, that
`mypy.ini` had no section for it, and that two tests under `tests/release/` were red about
exactly that. Every clause of it was true, and the last one is why the rest are no longer.**
The red held. Three distributions were unregistered, not one — `mainline_corpus`,
`mainline_demo_api`, and `cases`, the conformance corpus, whose module name does not begin
with `trappoint_` and whose *distribution* does, so its tier was an accident nobody had
decided. All three now carry a section, a tier and a measured count, and the ratchet
records 32 [src: qa/mypy-ratchet.json#distributions|len].

Two things about that repair are worth keeping. The first is that the CI job named
`mypy · and the target list is complete` was **green throughout** — it runs `--check`,
which asks whether every distribution has a section, and never `--ratchet`, which asks
whether the published number describes this tree. Two gates, two definitions of complete,
and the weaker one was the one wired to the board. The second is that the corrected
reading of the mypy rows is now the strong one — *what the workspace type-checks like* —
and it is only strong because the count of distributions is printed beside it. Drop that
number and the pair goes back to being a statement about whatever the checker happened to
be pointed at.

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

### The forward-only deployment runner wrote no artefact — RESOLVED, and here is the receipt

**This heading used to read "has been driven, and wrote no artefact", and the section
below it said "it still wrote no artefact under `qa/` or `evidence/`, so this page prints
no figure for it." Both sentences were true when written and are false now.** They are
corrected here rather than deleted, because the sequence is the evidence that the
mechanism works: the page refused to print a good result it could not cite, the artefact
was written, the checker went red on its own accord, and the prose moved.

The run is [`evidence/chain/chain-20260810T062542Z.json`](../evidence/chain/chain-20260810T062542Z.json)
and its numbers are in PROVEN above, where a completed deployment belongs. What remains
genuinely unrecorded is the **halt**: the earlier forward-only run that stopped at
`0121_trg_check_materialised` wrote no artefact and never will, so the *before* side of
this repair is prose in [`docs/STATE-OF-THE-BUILD.md`](STATE-OF-THE-BUILD.md) and no
figure for it is printed here.

The rule that made the awkward position correct is unchanged, and it is restated here
verbatim because it is the thing that just paid: *that is a deliberately awkward position
to leave a document in, and it is the correct one. The rule that makes this page worth
reading is that a quantity resolves to a machine-readable file; suspending it for a good
result would be exactly the move it exists to prevent.* **A measurement I cannot cite is a
measurement this page does not print, even when it is the best news in the wave.**

And the sentence that made the distinction worth drawing in the first place is still the
sharpest thing on this page, now that both numbers exist and agree: *the measurement
everyone quotes is not the measurement a deployment performs.* They coincide today. They
did not last week, and nothing guarantees they will next week.

> **This is what the deliberate breakage looked like from the inside.** `evidence/chain/`
> is a declared reference family in `tests/release/test_honesty_is_checkable.py`. The
> moment `chain-20260810T062542Z.json` appeared,
> `test_the_document_does_not_lag_a_family_that_landed` failed and named it — before any
> human noticed the artefact existed. The build was red because evidence had arrived that
> the prose had not absorbed, which is the correct colour for that condition. The same
> trap is still armed for every future run in that directory.

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

**"And no census has been taken. `qa/conformance-census.json` does not exist." That was
this page's sentence, and it is now false.** The census exists, it was taken against a
cluster with the whole tree applied, and it is
[`qa/conformance-census.json`](../qa/conformance-census.json). The result is worse reading
than the sentence it replaces, which is the reason to print it in full rather than to
summarise it.

| The conformance suite, run to completion, `v26.2.5` | |
|---|---|
| Cases the manifest declares | 71 [src: qa/conformance-census.json#run.manifest_declared_case_count] |
| Cases selected and attempted | 71 [src: qa/conformance-census.json#selected] |
| **PASSED** | 10 [src: qa/conformance-census.json#totals.passed] |
| **FAILED** — the gate answered, and answered wrongly | 6 [src: qa/conformance-census.json#totals.failed] |
| **CANNOT RUN** — nothing was ever asked of the gate | 55 [src: qa/conformance-census.json#totals.cannot_run] |
| ERRORED | 0 [src: qa/conformance-census.json#totals.error] |
| Left PENDING, i.e. never reached | 0 [src: qa/conformance-census.json#totals.pending] |
| Migrations applied to the cluster it ran against | 271 [src: qa/conformance-census.json#schema_state.applied] |

Cases that ended anywhere but PASSED and carry no reason naming an object:
0 [src: qa/conformance-census.json#completeness.cases_without_a_reason_naming_an_object|len].
A cannot-run without a named object is a shrug, and the census refuses to record one.

**Ten of seventy-one is the number, and it is not a pass rate about the gate.** Read the
middle three rows together. Only sixteen cases — the passes and the failures — put a
question to the database at all; the rest never got that far. The single largest cause is one
column: 46 [src: qa/conformance-census.json#systemic_causes.0.n] of the cannot-runs are
the legal world failing to build at `clause_version` because `body_sha256` does not exist,
and the census says so in those words, per case. That is one setup defect wearing
forty-six case identifiers, and counting it as forty-six failures would be as misleading
in this direction as counting it as zero.

The six FAILED are the interesting ones and none of them is a gate that let a write
through unnoticed by the suite: two are histories that COMPLETED where a refusal was
expected, one is a `23502` where a trigger should have projected the strictest legal value,
one is a `P0001` from a different function than the case named, one is a schema object the
migration that owns it has not created, and one is a syntax error in a case's own setup.
Each is quoted verbatim in the artefact. **A suite that reports six wrong answers is worth
more than a suite that reports none because it never ran.**

Six of the capability tokens name relations this repository has deliberately not authored
— `propagation`, `observed_assertion`, `merge_conflict`, `frontier_move`,
`discordance_warrant`, `coverage_certificate`. Those cases cannot pass and report
cannot-run with the object named, which is the designed outcome and not a defect.

**What this changes about the ranking.** This section used to end "this remains the single
largest gap between what this repository contains and what it has shown", and that
sentence was retired by the census rather than by an argument: the suite has now been
demonstrated, at a modest pass rate, against a migrated cluster. A demonstrated suite is a
categorically different artefact from an undemonstrated one, and this repository now has
the first kind. The largest remaining gap is the one the census itself names — the setup
path that costs forty-six cases — and it is a fixture defect, not a claim about the gate.

> **Same deliberate breakage as above, and it fired.** `qa/conformance-census.json` is a
> declared reference family; the moment the file appeared,
> `test_the_document_does_not_lag_a_family_that_landed` refused the build until this
> section was rewritten around its per-status totals. It will refuse again on the next
> census, and the totals above are the ones in the committed JSON.

### One target could not be measured at all

`tests/integration` under the cluster pass hit the census's own wall-clock ceiling. Its
counts in the JSON are a floor, not a measurement, and the row carries `timed_out: true`.
Targets in that state, cluster pass: 1 [src: qa/test-state.json#totals.cluster.timed_out_targets].
It was re-run with the ceiling raised to 2400 [src: qa/test-state.json#merges.0.per_target_timeout_seconds]
seconds and **still did not finish**, so the number of integration tests that pass against
a live database is, today, unknown. Without a database the same target reports its counts
in about a minute, which is the shape of a suite whose cluster path is doing far more work
than anyone has budgeted for.

### The licence count exists now, and this page still does not print it

**"`qa/reuse-ratchet.json` is not [on disk]." That was this section's claim and it is
false: the file is on disk.** So is `scripts/qa/check_reuse.py`, which the next paragraph
used to say was missing. Both sentences are corrected here rather than removed, because
what they were describing — a lane that could not start — is a different condition from
the one that holds now, and a reader who only saw the new text would not know the page had
been wrong.

**The figure is still not printed, and the reason has changed.** It is no longer "no
artefact re-derives it"; it is that the licence-spelling migration is *in flight*. Two
spellings are in use for the same forked identifier — `FSL-1.1-ALv2`, which is not an
SPDX-registered id, against the `LicenseRef-` form REUSE requires — and `LICENSES/` holds
both texts, so the tree is mid-migration rather than a fixed number of files short of
compliant. A count taken now would be a count of a half-finished rewrite, and freezing one
as a baseline is how a ratchet stops meaning anything. `qa/reuse-ratchet.json` is
deliberately not a declared reference family in
`tests/release/test_honesty_is_checkable.py` while that is true, which means this page is
*not* obliged to cite it and is not pretending to. When the migration completes, the
honest baseline is zero as a hard gate, and the family declaration and the figure land
together.

**The pipeline does start.** The sentence "the pipeline still cannot start, so every CI
number in this repository is a number about a lane that has not run" was true while
`scripts/qa/check_reuse.py` was absent and every substantive job declared
`needs: [checkers]`. The program exists, the `checkers` job passes, and lanes now run and
publish colours — several of them red, several green. This page prints no tally of that
because the tally lives in [`docs/CI-STATE.md`](CI-STATE.md), a prose document and not a
source a number may be drawn from here.

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
* **The reference vertical cannot be applied.** `trappoint_ref.clause` and
  `trappoint_ref.event` are referenced by the rendered SQL and created by no file in it, so
  `trappoint migrate up --tree trappoint-ref` refuses at `0058_blocking_check` with `42P01`
  and the conformance corpus reports `cannot_run` against that profile with the object
  named in every case. **This is the same defect class as the seven unproduced tables
  above, in the package that is supposed to be the forkable half**, and it is red in the
  `schema` workflow with the owning domain on it. `VERIFY.md` used to give that sequence as
  its headline Tier-2 command and no longer does.
* **The repository is public**, since `2026-08-11`, which changes what a stale claim costs
  rather than what one is. Every number on this page is now checkable by a stranger with no
  account, and the disclosure register of what the flip published — including the founder's
  local Windows account name in nine files, the AWS account id in commits already pushed,
  and the findings nobody has yet signed for — is `docs/submission/PUBLIC-READINESS.md`.
  None of it is a credential; all of it is disclosed on purpose or listed as owed.

---

## GEOGRAPHY AND LATENCY

**Inference is in Australia. The database is in Singapore. There is no end-to-end
Australian data residency, and any claim of it would be false.**

| | |
|---|---|
| Bedrock inference | `ap-southeast-2` (Sydney), `au.*` Claude inference profiles |
| Bedrock inference and Titan embeddings | **EXERCISED.** `invoke_model` on `amazon.titan-embed-text-v2:0` and `converse` on `au.anthropic.claude-haiku-4-5-20251001-v1:0` returned HTTP `200` with request ids, and the vectors were searched through a C-SPANN index. Transcripts: `evidence/aws/probe/bedrock-probe.json`; vectors and plan: `evidence/aws/ann/ann-proof.json`; an independent four-call probe with its own AWS request ids and `calls_failed: []` in `evidence/deploy/aws-live.json` |
| What that verdict does **not** cover | S3, KMS, CloudTrail, Lambda, CloudFront, IAM roles, SSM Parameter Store, EventBridge — and CloudWatch as provisioned infrastructure rather than as metrics read back. All still DESIGNED; `terraform apply` has never been run |
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
