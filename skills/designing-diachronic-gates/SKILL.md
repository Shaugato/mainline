---
name: designing-diachronic-gates
description: Designs and proves state-transition gates in CockroachDB that refuse a write because of the subject's history, not merely its current row. Use when a transition must be blocked until every outstanding obligation is discharged, when an approval rule needs a refusal the database enforces rather than the application, when a fact arriving after a completed transition must not be silently attachable, or when a constraint must be shown to actually refuse rather than assumed to. Covers the PROJECT/PIN/REFUSE idiom — a trigger projecting a cross-row fact onto a scalar column from an authoritative table, a composite foreign key under ON UPDATE RESTRICT pinning the completed transition to an epoch, and a plain-column CHECK over that scalar — plus why the constraint NAME is the deliverable, recovering an exhibit from P0001, and an unwelding matrix proving refusal depth. Includes a script that spins a throwaway node, replays an illegal history and fails unless the expected SQLSTATE and constraint name are raised.
license: Apache-2.0
---

<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Designing diachronic gates

## The distinction that decides everything

> A **synchronic** gate reads the row in front of it. A **diachronic** gate reads the
> subject's history and refuses on what that history contains.

Almost every "approval workflow" ships synchronic. It checks the fields on the record being
approved. It cannot express *"this may not close while an obligation raised three revisions
ago is still open"*, so that rule lives in application code — which means it lives in
**every** application, including the migration script, the back-office correction, the
support engineer's `UPDATE`, and the integration nobody remembered.

A diachronic gate is a rule the **database** holds. Written as below, it refuses for every
writer, forever, and the refusal is a named constraint a non-engineer can read.

## Three moves, in this order

```
PROJECT  a row-level trigger writes the cross-row fact onto a scalar column of the
         subject row, derived from an authoritative table and NEVER from the inserter
   ↓
PIN      the completed transition takes a composite FK onto (subject_id, epoch);
         a new obligation bumps the epoch; ON UPDATE RESTRICT makes attaching an
         obligation to a completed transition physically impossible
   ↓
REFUSE   a plain-column CHECK over the projected scalar refuses the write —
         for every writer, forever
```

Each move exists because the move before it is not sufficient on its own, and the order is
forced by what SQL can express.

### 1 · PROJECT — because a CHECK cannot see another table

`CHECK` constraints cannot contain subqueries. So the cross-row fact has to *already be a
scalar on the subject row* before the constraint can read it. That column is a
**materialised conflict**, not a cache:

```sql
CREATE FUNCTION fn_project_open_blocking() RETURNS TRIGGER LANGUAGE PLpgSQL AS $fn$
DECLARE v_blocking BOOL; v_count INT8;
BEGIN
  -- The authority relation decides what blocks. The inserter does not.
  SELECT sc.is_blocking INTO v_blocking
    FROM severity_class sc WHERE sc.severity = (NEW).severity;
  IF v_blocking IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'GATE: refused by fn_project_open_blocking — no severity_class row';
  END IF;
  ...
  UPDATE subject s SET open_blocking = v_count, gate_epoch = s.gate_epoch + 1
   WHERE s.subject_id = (NEW).subject_id;
  RETURN NEW;
END $fn$;
```

Three properties are load-bearing, and dropping any one of them produces a gate that looks
identical and is not one:

* **Derived from an authoritative table, never from the writer.** If a client can supply
  the value the gate reads, the client can open the gate. The severity is an input; whether
  that severity *blocks* is a lookup.
* **Absence of the authority row RAISES.** It does not default, infer, or admit-and-flag.
  A gate that admits when the evidence is missing is a gate that fails open on exactly the
  data quality problem it exists to survive.
* **`(NEW).col`, not `NEW.col`.** Measured on v26.2.5: the unparenthesised read form does
  not survive `CREATE TRIGGER`.

### 2 · PIN — because SERIALIZABLE calls a late arrival perfectly legal

Consider: the subject closes legally at 09:00 with zero open obligations. At 09:05 an
obligation for the same subject is inserted. Nothing in step 1 or step 3 refuses this. Both
transactions are correct; they do not conflict; `SERIALIZABLE` is satisfied. The subject is
now closed while carrying an open obligation, and **no row anywhere looks wrong**.

The fix is to make the completed transition depend on an epoch, and make a new obligation
change that epoch:

```sql
CREATE TABLE subject (
  subject_id    INT8 NOT NULL,
  gate_epoch    INT8 NOT NULL DEFAULT 0,
  ...
  CONSTRAINT subject_epoch_target UNIQUE (subject_id, gate_epoch)   -- the FK's target
);

CREATE TABLE completion (
  subject_id INT8 NOT NULL,
  gate_epoch INT8 NOT NULL,
  CONSTRAINT pk_completion PRIMARY KEY (subject_id),
  CONSTRAINT completion_pin FOREIGN KEY (subject_id, gate_epoch)
    REFERENCES subject (subject_id, gate_epoch) ON UPDATE RESTRICT ON DELETE RESTRICT
);
```

Once a `completion` row exists, `subject.gate_epoch` is **physically immutable**. The
projection trigger's epoch bump is an `UPDATE` on a referenced key, so `ON UPDATE RESTRICT`
refuses it. Verified on v26.2.5:

```
ERROR: update on table "s" violates foreign key constraint "completion_pin" on table "completion"
SQLSTATE: 23503
CONSTRAINT: completion_pin
```

The obligation is not *detected* after the fact. It **cannot be attached**. The declared
remedy for a genuinely new post-completion fact is therefore a fork — suspend the completed
subject, open a child whose gate is cleared afresh — which is a decision a human makes on
the record, not an `UPDATE` nobody sees.

`ON DELETE RESTRICT` too, and no cascade anywhere: a cascade rewrites history, which is the
offence this whole construction exists to detect.

### 3 · REFUSE — a plain-column CHECK, and its name is the deliverable

```sql
CONSTRAINT gate_closed_when_issued CHECK (state <> 'closed' OR open_blocking = 0)
```

No subquery, no trigger, no application. It refuses for every writer including the one
nobody anticipated, and it survives when the triggers are disabled.

**Write one named CHECK per rule, never one counter for all of them.** The constraint name
is what a reader is shown:

```
ERROR: failed to satisfy CHECK constraint ((state != 'closed':::STRING) OR (open_blocking = 0:::INT8))
SQLSTATE: 23514
CONSTRAINT: gate_closed_when_issued
```

`gate_closed_when_issued` is a sentence. `chk_subject_7` is not. When a refusal has to be
explained to somebody who does not read SQL — an auditor, a regulator, a customer's
counsel — the name is the entire explanation, and the expression printed beside it is
noise. Rules that would collapse into one counter should stay separate constraints for
exactly this reason.

## Do not let the trigger pre-empt the CHECK

A gate function must **not** `RAISE` for a condition a `CHECK` already refuses.

A synthetic `23514` from PL/pgSQL carries **no constraint name**, so it produces a refusal
nobody can name — the precise failure the whole design is avoiding. A synthetic `40001` is
worse: it is indistinguishable from a real serialization failure, so a correct client will
retry a deterministic refusal until its budget runs out.

Leave to the trigger only what no `CHECK` can hold:

1. a condition depending on `now()` — expiry, staleness, a bounded window;
2. a condition over the **absence** of a row in another relation;
3. a condition over an **aggregate** of another relation;
4. **drift** — a re-derived value disagreeing with the projected value.

Case 4 is the one people skip, and it is the one that matters. The projection trigger in
step 1 is armed on the *obligation* table, so a direct `UPDATE subject SET open_blocking = 0`
sails straight past it and the `CHECK` then reads a zero that is a lie. Verified: that
`UPDATE` succeeds. So the completing transition re-derives from the base tables and refuses
on disagreement:

```sql
CREATE TRIGGER subject_close_gate BEFORE UPDATE ON subject
  FOR EACH ROW WHEN ((NEW).state = 'closed' AND (OLD).state <> 'closed')
  EXECUTE FUNCTION fn_subject_close_gate();
```

**`BEFORE`, not `AFTER`.** The table's `CHECK` constraints are evaluated on the row the
function returns, so a `BEFORE` trigger runs first and an `AFTER` trigger could never refuse
anything the constraints had already passed. Measured in that order on v26.2.5.

**The `WHEN` clause belongs in the trigger definition, not as an early `return` in the
body.** A reader of `SHOW CREATE TABLE` sees the first; a future edit cannot quietly delete
it. It is also the acyclicity argument — every obligation write updates the subject row, so
an unrestricted merge gate would re-enter on every projection.

## Proving it — the unwelding matrix

A gate nobody has watched refuse is a hypothesis. Worse, a passing test suite that has never
been red asserts nothing at all: it is consistent with a schema in which the constraint was
silently dropped six migrations ago.

So prove two things, separately:

1. **The welded schema refuses, with the exhibit.** SQLSTATE *and* constraint name.
2. **Each mechanism is load-bearing.** Remove it and the illegal history is **ADMITTED**.

The second is the unwelding matrix. Run it with the bundled script — no arguments, no
cluster, no credentials; it starts a throwaway node and destroys it:

```bash
python scripts/assert_gate_refuses.py --self-test
```

Observed output against `cockroachdb/cockroach:v26.2.5` on 2026-08-10:

```
[PASS] welded                      close_with_open_obligation    23514 / gate_closed_when_issued
[PASS] welded                      attach_after_completion       23514 / gate_closed_when_issued
[PASS] welded                      disarm_the_counter            P0001 / fn_subject_close_gate (parsed)
[PASS] check_dropped               close_with_open_obligation    ADMITTED
[PASS] check_dropped_pin_survives  attach_after_completion       23503 / completion_pin
[PASS] pin_dropped                 attach_after_completion       ADMITTED
[PASS] projection_disabled         close_with_open_obligation    P0001 / fn_subject_close_gate
[PASS] gate_trigger_disabled       disarm_the_counter            ADMITTED
[PASS] fully_unwelded              close_with_open_obligation    ADMITTED
9 rows, 0 wrong, 4 of them proving the assertion can fail
```

Read the rows that are *not* `ADMITTED` after an unwelding. `check_dropped_pin_survives`
says: with the `CHECK` gone, the epoch pin refuses the same history by itself. That is
**refusal depth 2** — two independent mechanisms, so one bad migration does not open the
gate. Claim depth only where you have a row like that; a single mechanism asserted twice is
depth 1 with extra steps.

Against your own schema:

```bash
python scripts/assert_gate_refuses.py \
    --schema gate.sql --prelude legal_setup.sql --history illegal.sql \
    --expect-sqlstate 23514 --expect-exhibit gate_closed_when_issued
```

`--prelude` must **succeed**; `--history` must be **refused**. A harness that cannot tell
"the setup was rejected" from "the gate refused" will report a broken fixture as a working
gate. Exit `0` refused as asserted, `1` it did not, `2` the environment could not answer —
never `0`.

## Recovering the exhibit

| SQLSTATE | Raised by | `CONSTRAINT:` line | Exhibit |
|---|---|---|---|
| `23514` | a `CHECK` | present | the constraint name, verbatim |
| `23503` | a foreign key, incl. the epoch pin | present | the constraint name, verbatim |
| `23505` | a unique index or constraint | present | the index or constraint name |
| `P0001` | a trigger, UDF or procedure | **absent** | the raising object, from the message |
| `40001` | serialization failure | n/a | not a refusal — the transaction is *undecided* |

`P0001` carries no constraint name, so give every `RAISE` a message shape an exhibit can be
recovered from and use it everywhere:

```
<PREFIX>: refused by <schema>.<object> — <one sentence, lower case, no full stop>
```

A client that recovered the exhibit by parsing must record that the diagnosis was
**weakened**, so a run whose exhibits were inferred is never indistinguishable from a run
whose exhibits the server reported. The script does this: it prints `(parsed)`.

Two rules about the message itself. It must not contain a value taken from an untrusted
document — the message is rendered in consoles and written to logs. And it must name facts,
rows and rules, never a person's competence, honesty or intent.

## Pitfalls, ranked by how quietly they fail

| Pitfall | How it shows up |
|---|---|
| The gate lives in application code | Passes every test. The migration script, the support `UPDATE` and the new integration all bypass it, with no error anywhere. |
| The projected column is writable by the client | The gate is open to anyone who reads the schema. Nothing looks wrong. |
| No epoch pin | An obligation arriving after completion attaches cleanly. Both transactions are correct and `SERIALIZABLE` is satisfied. |
| Projection trigger armed only on the child table | A direct `UPDATE` on the subject zeroes the counter and the `CHECK` reads a lie. |
| Trigger `RAISE`s where a `CHECK` would fire | The refusal arrives as `P0001` with no constraint name — an exhibit nobody can cite. |
| Synthetic `40001` from a trigger | A correct client retries a deterministic refusal until its budget is exhausted. |
| `AFTER` instead of `BEFORE` on the gate trigger | The constraints have already passed; the re-derivation can refuse nothing. |
| One counter for six rules | The refusal is real and unexplainable. `chk_subject_7` tells a regulator nothing. |
| `ON DELETE CASCADE` anywhere on the lineage | Deleting a parent rewrites the history the gate reasons over. |
| Test asserts only the SQLSTATE | A typo in a column name raises `23514` too, and the suite calls it a working safety gate. |
| Suite has never been red | Consistent with the constraint having been dropped six migrations ago. |

## References

* `references/gate-anatomy.md` — the complete reference schema with per-object commentary,
  what each object refuses, and what happens when it is removed.
* `references/error-codes.md` — the closed refusal taxonomy, how each code recovers an
  exhibit, the synthetic-code ban, and why `40001` is the only retryable code.
* `references/unwelding.md` — how to build an unwelding matrix for a schema that is not
  this one, what refusal depth means and what it does not, and the traps in measuring it.
