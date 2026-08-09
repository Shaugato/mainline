<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# trappoint-model

**The oracle, the differential, the shrinkable interleaving, and the isolation downgrade.**

This package exists to *disagree with the gate*. Everything else in the kernel asserts
that a named history produces a named refusal; this asserts that **every** history
produces the refusal a second, independent implementation predicts — including the four
thousandth step of a history nobody wrote down.

It is a test instrument. Nothing in the substrate, the gate service or any Lambda imports
it, and it imports nothing from the substrate either. That second half is the load-bearing
one: see §1.

---

## 1. Why a model, and why it must be small

You cannot write down, in advance, the correct refusal for an arbitrary generated history.
That is the **oracle problem**, and the usual answers — assert an exception was raised,
assert nothing crashed — are worthless in a product whose deliverable is a *diagnosis*.

Differential testing sidesteps it. Two independent implementations of the same rule are
run on the same input and compared. A disagreement is a bug in one of them, and nobody has
to say which in advance.

Two constraints make that argument valid, and both are asserted by
`tests/test_model_pure.py` rather than promised:

**`model.py` is ≤ 200 lines.** An oracle nobody can hold in their head cannot be used to
accuse an implementation — you would not know which side to believe. At 193 lines it is a
five-minute read. If it ever needs four hundred, the model is wrong, not the gate.

**`model.py` imports nothing but `dataclasses`.** In particular it does not import
`trappoint-core`, and `adapter.py` therefore re-implements twelve lines of exhibit
recovery that `trappoint_core.errors.diagnose` also implements. That duplication is the
price of independence: an error shared between the client and the model would cancel out
in the comparison and the differential would agree, loudly, about nothing.

**The comparison is on the exhibit, not just the outcome.** A verdict is
`(sqlstate, constraint)`. A model that predicted only "refused" would agree with a gate
that refused everything for the wrong reason, and the constraint name is the courtroom
exhibit.

---

## 2. What runs against what

The differential runs against the **rendered reference vertical** —
`packages/trappoint-sql/refvertical/sql/`, 109 files, applied one statement at a time
exactly as `trappoint migrate` would. Not a reduction, not a hand-written schema: the same
templates the MAINLINE binding renders from.

`refschema.py` supplies six **stand-in relations** the reference vertical's own SQL names
but its file list does not contain (`event`, `clause`, `site`, `ledger_intake`,
`event_severity_revision`, `trappoint_ref_meas.recall_policy`), plus the `trappoint`
bootstrap schema. Without them 23 of the 109 files fail to apply and the unapplied set is
the entire gate. Every stand-in is a *dependency* of a mechanism and never a mechanism:
`tests/test_refschema.py` locks the list by count and content, refuses any stand-in
carrying a `CHECK`, `REFERENCES`, `TRIGGER` or `UNIQUE`, and **fails on the good news** —
the day the render worker ships one of these relations, the test fails and the stand-in
must be deleted.

| Component | What it is |
|---|---|
| `model.py` | the oracle: subjects, obligations, dispositions, epochs, `apply(op) -> Accept \| Refuse` |
| `adapter.py` | the same eight operations against a real cluster, returning the same vocabulary |
| `machine.py` | the Hypothesis `RuleBasedStateMachine` that runs both and compares |
| `invariants.py` | L1/L2/L3 and four structural invariants, fused into one round trip |
| `scheduler.py` | interleavings as shrinkable data, one token, one statement at a time |
| `programs.py` | the two transaction programs the scheduler races |
| `refschema.py` | the tree applier, the stand-in list, the tenancy seeder |
| `cluster.py` | discovery, and the skip contract |
| `replay.py` | the durable counterexample record, replayed deterministically |
| `profiles.py` | `ci` / `nightly`, and Hypothesis's own example database |

---

## 3. The eight operations, and the one modelling decision in them

`create_subject` · `fork_child` · `materialise_check` · `sign_disposition` ·
`expire_override` · `retract` · `attempt_merge` · `suspend`.

Nothing in the kernel moves `permit.state` except `merge_permit` itself. The column is the
*application's* record of where the subject is, and `legal_edge` — a composite foreign key
into `subject_transition` — is the database's opinion of whether that record is reachable.
So the adapter has to play the gate service and record transitions, and it records exactly
two:

* `draft → checks_materialised`, when the first obligation lands;
* `checks_materialised → dispositioned`, when the last one is cleared.

The re-opening edge `dispositioned → checks_materialised` is legal in `subject_transition`
and is **deliberately not recorded**. That is what makes an obligation arriving *after*
clearance meet `gate_closed_when_issued` — the projected counter alone standing between an
open obligation and a merge, which is conformance case CF-01 and the entire claim of the
product.

Both are expressed as SQL predicates (`WHERE p.state = '<from>' AND (<guard>)`), never as
a Python `if`, so a statement that matches no row writes nothing and the decision stays in
the database.

`expire_override` deserves a note. It signs a verdict whose `expires_at` is already in the
past — legal at insert, because `ttl_enforced` bounds the far end of the window and not the
near one. No sleeping, no clock control, fully shrinkable. The counter decrements while the
anti-join keeps counting, so `open_blocking` reads zero and the derivation reads one: the
case no `CHECK` over a scalar can see, and the reason `fn_permit_merge_gate` exists.

---

## 4. What the differential found

These are measurements against **CockroachDB CCL v26.2.5**, dated **2026-08-09**. Where a
migration header or a design document says otherwise, the measurement is what the model
encodes and the disagreement is recorded here rather than smoothed over.

**F-M1 · A post-merge retraction is refused by the COUNTER, not by the pin.**
`0104_fn_disposition_retract_only.sql`'s header states: *"23503 on the epoch pin when the
subject has already merged — which is the point."* Measured, it is **`23514` on
`gate_closed_when_issued`**. The trigger bumps both `open_blocking` and `gate_epoch` on the
subject row; the row's own `CHECK` is evaluated before the composite foreign key, so the
counter fires and the pin never gets to. Refusal depth is 2 either way and MI07 survives
intact — but the *exhibit* is the counter's. `23503 epoch_pin_permit` is observed on the
neighbouring path: a subject that merged and was then **suspended** satisfies
`state <> 'merged'`, the counter's CHECK passes, and the epoch bump reaches the pin. Both
branches are in `Model.retract` and both are exercised on every run.

**F-M2 · `cluster_logical_timestamp()` is unsupported at READ COMMITTED** — `0A000`,
verbatim. Two consequences. Blame-closure seeding cannot run on the downgraded connection,
because `fn_closure_guard` records the closure in the custody ledger in the same
transaction; the differential therefore seeds authority-source rows on a second
SERIALIZABLE connection, which is fixture setup and not the gate. And **MAINLINE's own
`merge_permit` calls it too**, in step 7's ledger intake — so on the MAINLINE binding a
merge at READ COMMITTED is refused by the ledger's clock before the gate is reached. The
downgrade evidence in this package is for the reference vertical, where step 7 is not
rendered. `test_read_committed.py::test_the_measured_platform_limit_still_holds` re-measures
the limit every run and is written to fail on the good news.

**F-M3 · The `FOR UPDATE` anchor serialises a parallel merge completely.** N ∈ {8, 16, 32,
64} all returned one winner and *N − 1* × `23503 legal_edge`. No `40001`, no `23505`. Step
1 of `merge_permit` queues the callers, so each loser reads `state = 'merged'` after the
winner commits and is refused by the transition table. The lock comment — *"lock ordering
and retry-thrash reduction only, never correctness"* — is doing what it says, and the retry
budget is not under pressure at these N. It also means **`merge_record_pkey` (CF-09) is a
structural backstop this race does not reach**; its depth belongs to the unwelding matrix
and this lane must not be cited for it.

**F-M4 · Expiry does not free the `one_live_disposition` slot.** The partial unique index
is over `retracted_by IS NULL`, so an expired verdict still occupies the slot while it has
stopped covering the obligation. Signing over an expired verdict is `23505`; clearing the
obligation requires a retraction first. The asymmetry is correct and it is the whole of
`_Obligation.live` versus `_covered()` in the model.

**F-M5 · The reference vertical does not apply on its own.** Six relations short; see §2.
Reported as a cross-domain note to the render worker, not fixed here — a differential that
hand-edited the tree under test would be asserting its own work.

---

## 5. Interleavings without threads you cannot shrink

Threads spawned inside a test give you concurrency and take away shrinking: a forty-step
failure stays a forty-step failure because the interleaving was never recorded.

So the schedule is **generated**. `interleavings(n)` emits a list of actor ids;
`TxnScheduler` holds one open transaction per actor, each on its own thread, and passes a
token so exactly one statement executes at a time in the generated order. Because the
schedule is ordinary shrinkable Hypothesis data, a forty-step counterexample reduces to the
three-step interleaving that actually breaks the gate.

This is the achievable form of deterministic simulation against a hosted database. You
cannot determinise CockroachDB's clock, its leaseholders or its internal retries — and you
do not need to, because **the invariant is DB-side**. What you can determinise is your side
of the wire, and that is enough to make a counterexample a recipe.

`BLOCKED` is a first-class outcome: an actor still waiting on a lock past
`block_timeout_s` is recorded and the scheduler advances. While it waits its statement *is*
in flight beside the next actor's — the one-statement-at-a-time property is a property of
the unblocked path, and a scheduler that pretended otherwise would deadlock on the first
lock conflict. `TIMED_OUT` (`57014`) and `ABORTED` (`25P02`) are recorded distinctly,
because they are the harness's own bounds firing and asserting the gate's taxonomy over
them would fail the lane on its timeouts.

**One deviation from the brief, stated plainly.** The generated element is an actor id, not
an `(actor_id, step)` pair. A transaction runs its own statements in order, so the only
legal step for an actor is the one after the last it executed; generating it too would
double the search space with values that are either redundant or invalid, and Hypothesis
shrinks a smaller space better. `Trace.pairs()` reconstructs the pair form for reports, so
the artefact exists — it is derived rather than drawn.

---

## 6. Running it

```bash
# Everything, against a local node (the fast loop).
TRAPPOINT_DSN='postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable' \
  uv run pytest packages/trappoint-model tests/concurrency

# The nightly profile: 2000 examples x 120 steps, plus the READ COMMITTED differential
# and the 64-way race.
TRAPPOINT_HYPOTHESIS_PROFILE=nightly TRAPPOINT_NIGHTLY=1 uv run pytest ...
```

With no `TRAPPOINT_DSN`, `cluster.py` starts a `cockroach` binary from `PATH`, or a
`cockroachdb/cockroach:v26.2.5` container — the exact Cloud version. With none of the
three the cluster-backed lanes **skip with a reason naming what is missing**, and the skip
message says in as many words that a skipped run is not evidence. The pure-oracle tests
always run.

A node this package starts is configured `gc.ttlseconds = 4500`, Cloud Basic's value.
Local defaults to 14400, which is *more permissive than production*; where the two differ,
local is configured to the stricter value by construction rather than by remembering.

| profile | `max_examples` | `stateful_step_count` | where |
|---|---|---|---|
| `ci` | 50 | 25 | every push, ~75 s |
| `nightly` | 2000 | 120 | `.github/workflows/nightly-differential.yml` |

`deadline=None` on both: a per-example wall-clock deadline against a real cluster measures
the cluster's mood, and a flaky failure in a suite about refusals teaches people to ignore
it.

---

## 7. The corpus is an artefact, in two halves

`.hypothesis-corpus/` is committed to git. For a product selling auditability, the
accumulated set of histories that once broke the gate is part of the assurance case.

It has **two halves**, and the split is a correction rather than an elaboration.
`DirectoryBasedExampleDatabase` is a cache of *currently-failing* examples: the moment a
counterexample stops reproducing — which is the moment you fix the bug — Hypothesis
deletes the entry. Measured, not assumed: three shrunk counterexamples were on disk while
the model was wrong, and the directory was **empty on the first green run**. Committing
only that directory preserves nothing about the bugs already fixed, which is exactly the
set a reviewer asks about.

| half | what it is |
|---|---|
| `counterexamples.jsonl` | the **regression record**: shrunk histories with the verdict every step must produce, replayed deterministically by `tests/test_regression_corpus.py` against the oracle always and the cluster when reachable |
| `<hash>/` | Hypothesis's own live, self-pruning database — replayed before generation, uploaded as a CI artefact, and *not* the regression record |

The recorded verdict is stronger than the differential that produced it: a differential
asserts *agreement*, and two implementations that made the same mistake agree perfectly.
Every entry also carries a `diagnosis` naming **which side was wrong**, asserted non-empty,
because that is the sentence that stops the next reader from editing the model to match
the cluster.

**No `GitHubArtifactDatabase`.** The design note proposed multiplexing a read-only
GitHub-artefact database as the second leg. It needs a token and a network call on every
test session, and `PL-1` says a milestone's proof must run on a stranger's machine with no
credential of ours. `nightly-differential.yml` uploads the corpus as an artefact instead —
same recovery path, no credential on the inner loop.

`.hypothesis-corpus/README.md` carries the prose log: five entries, C-001 to C-005.

---

## 8. What this package does NOT prove

Stated because a claim that overreaches its evidence is the thing this domain exists to
make impossible.

* **L2 and L3 are not evaluated here.** `identity_residue` and `silence_ledger` belong to
  the ancestry and recall domains and the reference vertical does not carry them.
  `check_all` returns them in its `not_applicable` list and the machine prints it. They are
  implemented and will evaluate against a binding that ships them.
* **Only the `permit` subject is exercised.** The substrate is subject-polymorphic and
  `change_request` has its own gate function, its own epoch pin and its own merge
  procedure — rendered from the *same* templates, under the same binding, which is what
  makes covering one a meaningful sample rather than half the job. It is still a sample:
  `--profile trappoint-ref`'s corpus is what covers the second kind, and a defect confined
  to `fn_cr_merge_gate` would not be found here.
* **The state machine is sequential.** It says nothing about interleavings; that is
  `scheduler.py` and `tests/concurrency/`.
* **The READ COMMITTED evidence is for sequential histories on the reference vertical.**
  See F-M2.
* **Refusal depth is not measured here.** Depth is the unwelding matrix's claim, and this
  package observes only which mechanism fired *first*.
* **A skipped run proves nothing**, and the skip message says so.

---

## 9. What has actually been run, and the gap to the exit criterion

The K1 exit criterion asks for **≥ 10⁶** generated operations at SERIALIZABLE and **≥ 10⁵**
at READ COMMITTED. That is a *nightly-lane* budget, not a single invocation, and the
distance is arithmetic rather than doubt:

| | measured |
|---|---|
| throughput, one operation = one round trip to a local single node | **≈ 17 ops/s** |
| `ci` profile, one class | 50 × 25 ≈ **1.25 × 10³** ops, ≈ 75 s |
| `nightly` profile, one class | 2000 × 120 ≈ **2.4 × 10⁵** ops, ≈ 4 h |
| 10⁶ at SERIALIZABLE | ≈ **4 nightly runs**, or ≈ 16 h of one machine |

So: the `ci` profile is green on every push and the `nightly` lane reaches 10⁵ at READ
COMMITTED in a single scheduled run and 10⁶ at SERIALIZABLE across the first week of them.
**Nothing in this repository may cite 10⁶ until a nightly run has recorded it** — the
number belongs in a CI job summary, not in a README, and this table exists so the claim is
checkable rather than asserted.

What *is* recorded so far: zero L1 violations, zero no-fork / counter-fidelity /
drift-direction / ledger-density violations, and zero model–cluster disagreements at both
isolation levels — **after** the three disagreements in §4 were found and resolved, each of
which is now a line in `.hypothesis-corpus/counterexamples.jsonl`. L2 and L3 are reported
NOT APPLICABLE against this binding and are not counted as passes.

---

## 10. If the model and the cluster disagree

**File the counterexample. Do not edit the model to match.**

Hypothesis has already written the shrunk example into `.hypothesis-corpus/` by the time
you read the failure, and `print_blob=True` gives you a `@reproduce_failure` decorator.
Establish which side is wrong before changing either. Every finding in §4 arrived this way,
and each one is a sentence in a design document that was not true of the running system —
which is exactly what a differential is for.
