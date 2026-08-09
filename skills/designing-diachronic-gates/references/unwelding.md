<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# The unwelding matrix — proving a gate is load-bearing

A green gate suite is compatible with a schema in which the constraint was dropped six
migrations ago and something else happens to be refusing. The unwelding matrix is the
cheapest way to rule that out: **remove one mechanism at a time and require the illegal
history to be ADMITTED.**

If removing a mechanism changes nothing, one of two things is true, and both are worth
knowing before a customer finds out:

* the mechanism is redundant — fine, if you *meant* that, and it is then depth, not waste;
* the refusal you have been attributing to it was coming from somewhere else entirely.

---

## Building one for your own schema

For each illegal history in your suite:

1. **Name the mechanism you believe refuses it.** Not "the gate" — the constraint, the
   foreign key, or the trigger, by name.
2. **Write the minimal unwelding** that removes exactly that mechanism.
   `ALTER TABLE … DROP CONSTRAINT …` and `ALTER TABLE … DISABLE TRIGGER …` are both
   available on CockroachDB v26.2 and both are what you want: reversible, scoped, and
   applied to a throwaway database rather than to anything real.
3. **Predict the outcome.** `ADMITTED`, or a *different* named refusal.
4. **Run it and require the prediction.** A row you cannot predict is a row you do not
   understand.

The prediction step is the whole exercise. A matrix that merely records what happened is a
changelog; a matrix that records what you expected and then checks it is a test.

---

## Reading the shipped matrix

```
variant                     case                        expected → observed
welded                      close_with_open_obligation  23514 / gate_closed_when_issued
welded                      attach_after_completion     23514 / gate_closed_when_issued
welded                      disarm_the_counter          P0001 / fn_subject_close_gate (parsed)
check_dropped               close_with_open_obligation  ADMITTED
check_dropped_pin_survives  attach_after_completion     23503 / completion_pin
pin_dropped                 attach_after_completion     ADMITTED
projection_disabled         close_with_open_obligation  P0001 / fn_subject_close_gate
gate_trigger_disabled       disarm_the_counter          ADMITTED
fully_unwelded              close_with_open_obligation  ADMITTED
```

Four rows end in `ADMITTED`. **Those are the rows that make the other five mean anything.**
A matrix with no admissions has not demonstrated that the harness can fail; it has
demonstrated that it did not.

Two rows are more interesting than the admissions:

* `check_dropped_pin_survives` — the same illegal history, the `CHECK` removed, and the
  epoch pin refuses it **by itself** with a different code and a different name.
* `projection_disabled` — the projection trigger removed, and the re-derivation at the
  completing transition catches the resulting drift.

Each of those is a genuine second mechanism, discovered by removing the first.

---

## What refusal depth is, and what it is not

**Depth *n* for a history means: *n* mechanisms each refuse it, and each does so with the
other n−1 removed.**

That last clause is the whole definition. Two constraints that both read the same projected
column are depth 1: one bad projection opens both. A `CHECK` and a foreign key that reach
the same conclusion through different data are depth 2 — verified above, because the pin
refuses when the `CHECK` is gone.

Things that are **not** depth:

* the same rule asserted in the application and in the database. The application is not a
  mechanism the database enforces; it is a mechanism *some* writers pass through;
* a trigger that raises for a condition a `CHECK` also refuses. At runtime only one of them
  fires, and if the trigger pre-empts, the refusal you get is the one with no name;
* two constraints on the same column with overlapping expressions;
* a constraint plus a monitoring alert. An alert is a notification about a state that was
  already accepted.

Claim depth only where a matrix row shows it. It is a claim about the schema, and it is
checkable, which means an unsupported version of it is an invitation.

---

## Traps in measuring it

**Do not unweld anything real.** The matrix creates and drops its own database on a throwaway
node. A schema-mutating harness pointed at a shared development cluster will eventually be
pointed at something worse.

**A failed unwelding statement is not a passing row.** If `ALTER TABLE … DROP CONSTRAINT`
itself errors, the schema was never weakened and the row proves nothing. Treat it as an
environment failure and exit non-zero — `assert_gate_refuses.py` raises rather than judging.

**A refused prelude is not a refused history.** If the *legal* setup is rejected, the
illegal history never ran. A harness that cannot distinguish those two will happily report a
broken fixture as a working gate — which is the most expensive kind of green there is.

**Disabled is not dropped.** `DISABLE TRIGGER` leaves the object in `SHOW CREATE TABLE`, so
a drift-detection check that reads the schema text will not notice it. If you rely on schema
fingerprinting to detect unwelding in production, fingerprint the *enabled* state of every
trigger, not just the DDL.

**Re-welding validates.** Adding a constraint back to a table that accumulated illegal rows
while it was dropped fails validation and names an offending row. Good — but that error is a
validation error and carries no `CONSTRAINT:` line, so a harness that assumes every `23514`
names a constraint will report no exhibit for it.

---

## Where the matrix belongs

Run it in CI, on a schedule, and after every migration that touches a gated table — the
migration is the realistic way a weld gets removed, and it is usually removed by somebody
solving an unrelated problem at speed.

Keep it out of the pull-request path only if it is slow. The shipped matrix runs nine
histories against nine freshly created databases on one throwaway node; that is a couple of
minutes, which is affordable nightly and usually affordable per PR.
