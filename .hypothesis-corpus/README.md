<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `.hypothesis-corpus/` — the counterexample corpus, committed on purpose

For a system that sells auditability, the accumulated set of histories that once broke the
gate is part of the **assurance case**, not build detritus. It records what was tried, what
failed, which side was wrong, and what is now permanently regression-covered. So this
directory is committed to git, and `.gitignore` deliberately covers only `.hypothesis/`
(the cache) and not this.

It has **two halves that do different jobs**, and the split is a correction to the obvious
design rather than an elaboration of it.

---

## 1. `counterexamples.jsonl` — the regression record

One JSON object per line; `//` lines are comments. Each is a shrunk history with the
verdict **every step must produce**, replayed deterministically by
`packages/trappoint-model/tests/test_regression_corpus.py` — against the oracle always,
and against a cluster whenever one is reachable.

The recorded verdict is *stronger* than the differential that produced it. A differential
asserts agreement, and two implementations that made the same mistake agree perfectly.
These assert the answer.

Handles are small integers so a history is readable:

```json
{"op": "retract", "disposition": 2, "by": 1, "expect": ["23503", "disposition_retracted_by_fkey"]}
```

**Append; never edit an entry.** An edited expectation is a regression test rewritten to
pass, which is the failure mode this file exists to prevent. To retire an entry, delete the
whole line and say why in the log below.

Every entry carries a `diagnosis` and the field is asserted non-empty, because it holds the
one sentence that matters to the next reader: **which side was wrong**. Without it, someone
will eventually "fix" the model to match the cluster and the differential will stop being
one.

## 2. `<hash>/` — Hypothesis's own directory

Live, self-pruning, and **not** the regression record.
`DirectoryBasedExampleDatabase` is a cache of *currently-failing* examples: the moment a
counterexample stops reproducing — which is the moment you fix the bug — Hypothesis
deletes the entry.

That was measured, not assumed. Three shrunk counterexamples sat here while the model was
wrong; the directory was **empty** on the first green run. Committing only this directory
would preserve nothing about the bugs already fixed, which is exactly the set an assurance
reviewer asks about. Hence half 1.

What this half is still good for: Hypothesis replays every entry **before** it generates
anything new, so a counterexample found on a laptop is the first thing the next CI run
tries; and `nightly-differential.yml` uploads the directory as an artefact, so a failing
nightly hands you the shrunk example.

**Do not hand-edit or prune the binary files.** They are keyed by a hash of the test's
identity; a file whose name no longer matches its content is never replayed, which turns a
regression test into a silent no-op.

---

## Log

Newest first. Each entry corresponds to a line in `counterexamples.jsonl`.

### C-005 · CF-01 in miniature — recorded, not a defect

The canonical arc: obligation → signature → **second obligation after clearance** → merge
refused `23514 gate_closed_when_issued` → signature → merge admitted → post-merge precursor
refused `P0001 fn_check_materialised` → second merge refused `23503 legal_edge`.

Recorded because the product's headline claim deserves a fixed expectation rather than an
agreement check. The subject stays in `dispositioned` when the second obligation lands —
the re-opening edge is legal in `subject_transition` and the service does not record it —
so the projected counter is the only thing between that write and a merged permit carrying
an open precursor.

### C-004 · expiry does not free the `one_live_disposition` slot

*Found 2026-08-09. **The model was wrong.***

The oracle treated "covers the obligation" and "occupies the slot" as one predicate.
`one_live_disposition` is a partial unique index over `retracted_by IS NULL`, so an expired
verdict still **holds** the slot while it has stopped **covering** the obligation. Signing
over it is `23505`; clearing the obligation needs a retraction first. Fixed by splitting
`_Obligation.live` from `_covered()`. The same asymmetry is what makes the drift case
reachable at all, so getting it wrong would have hidden `fn_permit_merge_gate`'s whole
reason for existing.

### C-003 · a retraction naming a disposition whose INSERT was refused

*Found 2026-08-09, SERIALIZABLE, `ci` profile, shrunk to 7 steps. **The model was wrong.***

A refused `sign_disposition` still put its id into the Hypothesis bundle, so a later
`retract` named it as the **retractor**. The cluster refused `23503` on
`disposition_retracted_by_fkey`; the oracle predicted `Accept`, having no notion that
`retracted_by` must reference a row that exists.

Fixed by the fifth branch of `Model.retract`, in the order measured on v26.2.5:
already-retracted (`P0001`) → merged (`23514 gate_closed_when_issued`) →
suspended-after-merge (`23503 epoch_pin_permit`) → reflexive
(`23514 retraction_not_reflexive`) → absent retractor (`23503
disposition_retracted_by_fkey`). The ordering was established by direct probe, not by
reading the migrations.

### C-002 · a post-merge retraction is refused by the counter, not by the pin

*Found 2026-08-09, sequential smoke history. **The document was wrong; the gate is right.***

`0104_fn_disposition_retract_only.sql`'s header states *"23503 on the epoch pin when the
subject has already merged — which is the point."* Measured, it is **`23514` on
`gate_closed_when_issued`**: the trigger's `UPDATE` moves `open_blocking` and `gate_epoch`
together, and the subject row's `CHECK` is evaluated before its composite foreign key, so
the counter refuses and the pin never runs.

MI07 is intact and depth is still 2 — but the exhibit named in the migration header and in
conformance case CF-40 is not the one the runtime produces. Raised as a cross-domain note
to `kernel/projection-triggers` and `kernel/conformance-corpus`. The entry records **both**
branches: after `suspend`, `state <> 'merged'` satisfies the counter's CHECK, the epoch bump
reaches the pin, and `23503 epoch_pin_permit` is what comes back.

### C-001 · `cluster_logical_timestamp()` is unsupported at READ COMMITTED

*Found 2026-08-09, first run of the downgrade differential. **A platform limit.***

Not a gate failure and therefore **not replayable as a history**, so it has no line in
`counterexamples.jsonl`; it lives here and as a live re-measurement in
`test_read_committed.py::test_the_measured_platform_limit_still_holds`, which is written to
fail on the good news.

`materialise_check` seeds a blame closure first, and `fn_closure_guard` writes the custody
ledger in the same transaction using `cluster_logical_timestamp()`, which CockroachDB
v26.2.5 refuses under READ COMMITTED with `0A000`. Authority-source seeding moved to a
second SERIALIZABLE connection so the downgrade run is about the gate rather than the
ledger's clock. The wider consequence — MAINLINE's `merge_permit` calls the same builtin in
step 7, so the MAINLINE binding cannot merge at READ COMMITTED at all — is raised as a
cross-domain note to the custody domain.
