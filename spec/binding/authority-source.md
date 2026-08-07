<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The Authority Source Contract

**Normative.** TRAPPOINT `1.0.0-rc.1`. Schema: [`vertical.schema.json`](vertical.schema.json).

This is the compile-time form of specification rule **P-2**:

> A projection trigger MUST derive its value from a declared authority source, and MUST NOT derive it
> from the inserted row, from another row of the same table, or from any relation the inserting role
> may write.

As a rule in a document, P-2 is a discipline someone has to remember during code review. As an entry
in `vertical.toml`, it is a **build error**. This document says exactly what the entry means, what
the renderer does with it, and what it deliberately does not check.

---

## 1. The problem it solves

The single most common way a gate quietly stops working is not a deleted constraint. It is a column
that *looks* projected and is in fact supplied.

```sql
-- The gate reads this column:
CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0)

-- ... and the obligation that feeds it declares its own severity:
INSERT INTO blocking_check (..., severity, virulence) VALUES (..., 1, 'routine');
```

If nothing overwrites `severity` and `virulence`, the gate is enforcing a claim the writer made about
itself. Every constraint still exists; every test still passes; the invariant is gone. The failure is
invisible precisely because nothing is missing — a column is populated, a `CHECK` fires, a trigger
runs. What is absent is *authority*.

The Authority Source Contract makes that absence a thing the build can see.

---

## 2. The declaration

```toml
[[authority_source]]
projects    = ["blocking_check.severity", "blocking_check.virulence", "blocking_check.closure_gen"]
relation    = "mainline.clause_blame_current"
key         = ["clause_uuid", "commit_id"]        # columns of the PROJECTED ROW
key_columns = ["clause_uuid", "as_of_commit"]     # columns of the AUTHORITY RELATION
columns     = ["max_severity", "virulence", "closure_gen"]
on_missing  = "raise"          # the ONLY legal value
```

Read it as one English sentence:

> *The columns `severity`, `virulence` and `closure_gen` of `blocking_check` are projections of
> `max_severity`, `virulence` and `closure_gen` in `mainline.clause_blame_current`, looked up by
> matching the inserted row's `(clause_uuid, commit_id)` against the closure's
> `(clause_uuid, as_of_commit)`, and when that lookup finds nothing the write is refused.*

| Key | Meaning |
|---|---|
| `projects` | the gate columns this entry backs, relation-qualified; must exactly cover the templates' `@projects` pragmas |
| `relation` | the authoritative relation; schema-qualified |
| `key` | columns **of the projected row** used to look up the authority row, in order |
| `key_columns` | optional: columns **of the authority relation** matched against `key`, positionally. Defaults to `key` |
| `columns` | columns **of the authority relation** read, positionally corresponding to `projects` |
| `on_missing` | `"raise"`. There is no second value |
| `raise_via` | optional: `"p0001"` (default) or `"strictest_projection"` (§5) |
| `strictest` | required when `raise_via = "strictest_projection"`: the strictest legal value per column |

`projects` and `columns` are **positional**: `projects[i]` is written from `columns[i]`. `key` and
`key_columns` are positional the same way: `key[i]` of the projected row is matched against
`key_columns[i]` of the authority relation. The renderer refuses a length mismatch on either pair,
because a silent off-by-one here writes a severity into a generation counter and the gate keeps
working, wrongly.

**`key_columns` is not sugar, and omitting it from the schema was a defect.** The two sides of the
lookup are named differently in the one binding that matters: the projected row carries `commit_id`
and the closure carries `as_of_commit`. A renderer that assumed the names coincided would emit
`WHERE c.commit_id = NEW.commit_id` against a relation that has no `commit_id`, and the failure would
surface as `42703` at migration time — outside the refusal taxonomy entirely, which is the wrong
place to discover a binding error.

---

## 3. What `trappoint render` refuses

Each of these is a non-zero exit with a message naming the offending column or key. None of them is a
warning.

| # | Condition | Message shape |
|---|---|---|
| **A-1** | a template marks a column with `{# @projects <col> #}` and no `[[authority_source]]` lists it | `unbacked projected column: blocking_check.severity` |
| **A-2** | `on_missing` is anything other than `"raise"` | `authority_source.on_missing must be "raise" (got "default")` |
| **A-3** | `len(projects) != len(columns)` | `authority_source projects/columns length mismatch` |
| **A-4** | the same qualified column appears in two entries | `column projected from two authority sources: …` |
| **A-5** | an entry projects a column no template declares | `authority_source projects an unrendered column: …` |
| **A-6** | `relation` is unqualified, or names a table declared as a subject or obligation table in this binding | `authority relation must not be a gated relation of this binding` |
| **A-7** | `raise_via = "strictest_projection"` without a `strictest` value for every projected column | `strictest_projection requires a strictest value for …` |
| **A-8** | the binding's `spec_version` differs in MAJOR from the specification in `spec/` | `binding targets TRAPPOINT 2.x; this tree is 1.x` |
| **A-9** | `key_columns` is present and `len(key) != len(key_columns)` | `authority_source key/key_columns length mismatch` |

**A-6 is the rule with teeth.** If the authority relation is writable by the role that writes the
projected table, the projection is derived from the inserter with an extra step, and P-2 is violated
while every declaration looks correct. The renderer can check the *structural* half of this (the
relation is not itself a gated relation of this binding); the *privilege* half is checked at
migration time and asserted by a conformance case, because grants are not visible to a template
engine.

---

## 4. What the renderer emits

For the entry above, with `raise_via = "p0001"`:

```sql
-- @projects blocking_check.severity, blocking_check.virulence, blocking_check.closure_gen
-- @authority mainline.clause_blame_current (clause_uuid, as_of_commit) <= NEW (clause_uuid, commit_id)
-- @on_missing raise
CREATE FUNCTION mainline.fn_check_project() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE sev INT2; vir mainline.virulence_class; cgen INT8;
BEGIN
  SELECT c.max_severity, c.virulence, c.closure_gen INTO sev, vir, cgen
    FROM mainline.clause_blame_current c
   WHERE c.clause_uuid = NEW.clause_uuid AND c.as_of_commit = NEW.commit_id;
  IF sev IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no blame closure for this clause version — cannot arm a check';
  END IF;
  NEW.severity := sev; NEW.virulence := vir; NEW.closure_gen := cgen;
  RETURN NEW;
END $$;
```

Three properties of the emitted code are contractual:

1. **The assignment is unconditional.** There is no `IF NEW.severity IS NULL THEN` guard. A supplied
   value is overwritten whether or not it agrees, so a correct guess confers no privilege.
2. **The `IF … IS NULL THEN RAISE` block is not optional.** It is emitted from `on_missing`, and
   `on_missing` has one legal value, so the refusal cannot be configured away.
3. **The header comments are machine-readable**, so `trappoint render --check` and the migration
   linter can verify that the committed SQL still corresponds to the declaration that produced it.

---

## 5. `strictest_projection` — when the refusal has a better exhibit

Sometimes the missing authority row would, if present, feed a **constraint-backed** refusal. In that
case raising `P0001` from the trigger is the *worse* outcome: the write is refused either way, but a
`P0001` carries no constraint name, and the constraint name is the exhibit.

```toml
[[authority_source]]
projects   = ["disposition.req_compensating", "disposition.req_second_signer",
              "disposition.req_foreign_org", "disposition.req_predicate",
              "disposition.req_reassert", "disposition.min_signer_rank"]
relation   = "mainline.clearance_legal"
key        = ["virulence", "kind"]
columns    = ["req_compensating", "req_second_signer", "req_foreign_org",
              "req_predicate", "req_reassert", "min_signer_rank"]
on_missing = "raise"
raise_via  = "strictest_projection"
strictest  = { req_compensating = true, req_second_signer = true, req_foreign_org = true,
               req_predicate = true, req_reassert = true, min_signer_rank = 9 }
```

The trigger then projects the strictest values and returns the row; the real composite foreign key
`fk_clearance` fires with `23503` **and its name attached**. Two further benefits, both practical:

- it avoids `23502`, which a `NOT NULL` projection left unset would produce and which is outside the
  refusal taxonomy (spec P-4);
- the strictest values are themselves refusing, so if the foreign key were ever dropped the row would
  still be refused by `rank_floor`, `needs_second_signer` and the rest. That is a refusal depth of
  seven from one declaration.

`on_missing` is still `"raise"`. `raise_via` changes *how* the refusal is produced, never *whether*.

---

## 6. What the contract deliberately does not check

Stated so nobody reads more assurance into a green render than it carries.

- **It does not verify the authority relation is correct.** If a vertical points at the wrong table,
  the renderer will happily project from it. What the contract guarantees is that the projection has
  *a named, reviewable source* and that a missing row refuses — not that the source is the right one.
- **It does not verify grants.** A template engine cannot see `GRANT`. The rule that the authority
  relation must not be writable by the projecting role is asserted by a conformance case
  (`42501` when the wrong role attempts the write), not by the renderer.
- **It does not make the projection correct under concurrency.** That is the materialised-conflict
  property (spec §3.1) and it is proved by the concurrency cases, not here.
- **It does not survive someone editing the rendered SQL by hand.** `trappoint render --check` is a
  zero-diff assertion in CI precisely because the declaration is only binding while the committed SQL
  is what the declaration produced.

---

## 7. Why this lives in the binding and not in the templates

Because the substrate must not know what a vertical's authority relation is called, and the vertical
must not be able to write a gate template. The seam between them is one file, and the one thing that
file must say — before the renderer will emit a single line of gate SQL — is *where the truth comes
from, and what happens when it is absent.*

A binding that cannot answer that question does not get to render a gate.
