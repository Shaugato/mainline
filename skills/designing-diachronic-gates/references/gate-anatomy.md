<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Gate anatomy — the reference schema, object by object

The executable copy of this schema lives in `scripts/assert_gate_refuses.py`, which is
deliberately the single source of truth: a reference document that has drifted from the
thing it documents is worse than no document. Dump it with

```bash
python scripts/assert_gate_refuses.py --print-schema
```

Everything below was executed against `cockroachdb/cockroach:v26.2.5` on 2026-08-10. Where
a claim is ours rather than the platform's, it says so.

---

## The five objects and what each refuses

| Object | Kind | Refuses | Code |
|---|---|---|---|
| `severity_class` | authority table | nothing directly; it is what the projection is *derived from* | — |
| `fn_project_open_blocking` + trigger | projection | an obligation whose severity has no authority row | `P0001` |
| `gate_closed_when_issued` | plain-column CHECK | closing while the projected counter is non-zero | `23514` |
| `completion_pin` | composite FK, `ON UPDATE RESTRICT` | bumping the epoch of a completed subject | `23503` |
| `fn_subject_close_gate` + trigger | re-derivation | closing when the projection disagrees with the base tables | `P0001` |

---

## `severity_class` — the authority relation

```sql
CREATE TABLE severity_class (
  severity    INT8 NOT NULL,
  is_blocking BOOL NOT NULL,
  CONSTRAINT pk_severity_class PRIMARY KEY (severity)
);
```

Small, boring, and the reason the gate cannot be opened by a writer. The obligation row
carries a *severity*; whether that severity **blocks** is a property of this table. A writer
who wants a non-blocking obligation must change a policy row, not a payload field — and
changing a policy row is a visible, reviewable, gate-able act.

If your equivalent of this table can be written by the same role that writes obligations,
you have a policy the subject of the policy can edit. Split the grants.

---

## The subject row

```sql
CREATE TABLE subject (
  subject_id    INT8 NOT NULL,
  state         STRING NOT NULL DEFAULT 'open',
  gate_epoch    INT8 NOT NULL DEFAULT 0,
  open_blocking INT8 NOT NULL DEFAULT 0,       -- PROJECTED. Trigger-written, never supplied.
  CONSTRAINT pk_subject PRIMARY KEY (subject_id),
  CONSTRAINT subject_epoch_target UNIQUE (subject_id, gate_epoch),
  CONSTRAINT subject_counter_nonneg CHECK (open_blocking >= 0),
  CONSTRAINT gate_closed_when_issued CHECK (state <> 'closed' OR open_blocking = 0)
);
```

* `subject_epoch_target` exists **only** so the composite foreign key has something to
  reference. Without a `UNIQUE` on `(subject_id, gate_epoch)` the pin cannot be declared at
  all, and without the pin a post-completion obligation is a perfectly serializable history.
* `subject_counter_nonneg` looks like defensive noise and is not. A projection that can go
  negative is a projection whose arithmetic is wrong, and you want that to surface as a
  refusal at the moment it happens rather than as a gate that opens later.
* The gate `CHECK` is written `state <> 'closed' OR counter = 0`, not
  `counter = 0` — the constraint must permit every non-completing state. A gate that
  refuses the *draft* is not a gate, it is an outage.

---

## The projection trigger

Full text in the script. Three details are easy to get wrong:

**`(NEW).col`, not `NEW.col`.** Measured on v26.2.5: the unparenthesised read form does not
survive `CREATE TRIGGER`. This is a platform detail, not a style preference.

**`TG_OP` decides which row supplies the subject id.** On `DELETE` the `NEW` record does not
exist. Read `(OLD).subject_id` and `RETURN OLD`.

**The epoch bumps on `INSERT` of a *blocking* obligation, and only then.** Discharging an
obligation reduces the counter but must not bump the epoch: discharge is not a new
obligation, and bumping there would make every legal discharge collide with the pin.

The `RAISE` on a missing authority row is the P2 rule made executable:

```sql
IF v_blocking IS NULL THEN
  RAISE EXCEPTION USING ERRCODE = 'P0001',
    MESSAGE = 'GATE: refused by fn_project_open_blocking — no severity_class row for severity …';
END IF;
```

A trigger that silently treats a missing authority row as *non-blocking* converts a data
quality problem into an opened gate, which is the single most expensive way to fail.

---

## The pin

```sql
CREATE TABLE completion (
  subject_id INT8 NOT NULL,
  gate_epoch INT8 NOT NULL,
  CONSTRAINT pk_completion PRIMARY KEY (subject_id),
  CONSTRAINT completion_pin FOREIGN KEY (subject_id, gate_epoch)
    REFERENCES subject (subject_id, gate_epoch) ON UPDATE RESTRICT ON DELETE RESTRICT
);
```

`pk_completion` on `subject_id` alone is doing real work: it makes "at most one completion
per subject" a primary key rather than a rule somebody remembers. The composite FK is the
pin.

Observed refusal when a new obligation tries to bump the epoch of a completed subject, with
the gate `CHECK` dropped so the pin is the only mechanism left:

```
ERROR: update on table "s" violates foreign key constraint "completion_pin" on table "completion"
SQLSTATE: 23503
DETAIL: Key (subject_id, gate_epoch)=(1, 1) is still referenced from table "completion".
CONSTRAINT: completion_pin
```

Note `table "s"` in the message: that is the **alias** from the projection trigger's
`UPDATE subject s …`, not a table name. Parse the `CONSTRAINT:` line, never the message.

---

## The re-derivation

```sql
CREATE TRIGGER subject_close_gate BEFORE UPDATE ON subject
  FOR EACH ROW WHEN ((NEW).state = 'closed' AND (OLD).state <> 'closed')
  EXECUTE FUNCTION fn_subject_close_gate();
```

Both conjuncts matter. The first restricts the function to the completing transition, which
is the acyclicity argument: every obligation write updates this same row, so an
unrestricted gate would re-enter on every projection and be evaluated in states it was never
designed for. The second stops a re-close of an already-closed subject from re-running the
gate — `UPDATE … SET state = 'closed'` against a row already in that state is a legal
statement.

The body refuses on **drift only**:

```sql
IF v_derived <> 0 AND (NEW).open_blocking = 0 THEN RAISE … END IF;
```

The `AND (NEW).open_blocking = 0` is the part that keeps the exhibit good. If the counter is
also non-zero then `gate_closed_when_issued` refuses this write with its own name attached,
and trading that named exhibit for an unnamed `P0001` is a strictly worse refusal. The
trigger declines to pre-empt the constraint, on purpose.

---

## Why the drift check is not optional

The projection trigger is armed on `obligation`. It is therefore blind to this:

```sql
UPDATE subject SET open_blocking = 0 WHERE subject_id = 104;   -- succeeds
```

Verified: that statement succeeds against the welded schema. The counter now reads zero
while a severity-5 obligation is undischarged, and `gate_closed_when_issued` — reading only
the scalar — would let the subject close. The re-derivation is what refuses it:

```
ERROR: GATE: refused by fn_subject_close_gate — re-derived open obligation count is 1
       while the projected counter reads zero
SQLSTATE: P0001
```

Two lessons generalise:

1. **Every column a gate reads needs a defender on the subject table too**, not only on the
   table it is derived from. Either re-derive at the transition, as here, or add a `BEFORE
   UPDATE` trigger on the subject that refuses any change to the projected columns that did
   not come from the projection path.
2. **`REVOKE UPDATE (open_blocking, gate_epoch)` on the subject table** from every role that
   is not the projection owner. Column-level grants make the direct write impossible for
   most writers, and the drift check catches the rest. Neither alone is enough; the grant
   does not bind the owner, and the drift check only fires on the completing transition.

---

## Re-welding over existing data validates it

Adding the constraint back to a table that accumulated illegal rows while it was dropped
fails, and the failure names the row:

```
ERROR: validation of CHECK "(state != 'closed':::STRING) OR (open_blocking = 0:::INT8)" failed
       on row: subject_id=3, state='closed', gate_epoch=1, open_blocking=1
SQLSTATE: 23514
```

This is useful and it is a trap. Useful: it is how you discover what an unwelded window let
through. Trap: the error is a *validation* error, so it carries no `CONSTRAINT:` line, and a
harness that assumes every `23514` names a constraint will report no exhibit here. Plan the
re-weld as a migration that first reports the offending rows and asks a human what they are,
because "the gate was open for four days" is a question with a factual answer that somebody
will eventually have to give.
