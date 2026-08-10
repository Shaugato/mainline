<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `producer-absent` — the observed red

**Artefact:** `producer-census-before.json`
**Rule:** `producer-absent`, implemented in
`packages/trappoint-migrate/src/trappoint_migrate/producers.py`, wired into
`trappoint migrate lint` as rule D.
**Captured:** 2026-08-10, by W1 of the producer-completion wave
(`docs/leads/producers-plan.md`).

---

## What this file is

**It is the red.** Not a description of a red, not a test that would go red: the output of
running the rule over the MAINLINE migration tree *before* the wave authored the tables it
was called to author.

This exists because of PL-2. A guard that has only ever run green is a guard nobody has
evidence works — you cannot tell a rule that is watching from a rule whose regex never
matches anything. The red run is the evidence that this one was live, and the artefact is
where it is kept so that nobody has to take the claim on trust.

**The exit condition is that the same command over the same tree reports zero.**

```
trappoint migrate lint --root verticals/mainline/db/migrations
```

---

## What was measured, and on which tree

The tree the red describes is the 261-file tree at commit
**`bb21962f188fa1c23a231463018282b3c2959bf0`**. It was materialised into a scratch
directory rather than read from the working tree, and the reason is written into the
artefact as well as here:

> W2–W5 began landing producer migrations into the working tree while this census was
> being taken.

By the time the rule existed, the working tree was no longer the tree the red was about.
Reading it anyway and calling the result "before" would have been the small dishonesty
that makes every other number in the repository worth less. The commit **is** that tree,
byte for byte, and anyone can reproduce the run from it:

```sh
git archive bb21962f188fa1c23a231463018282b3c2959bf0 \
    verticals/mainline/db/migrations verticals/mainline/db/migrations.allocation.toml \
  | tar -x -C /tmp/head261
trappoint migrate lint --root /tmp/head261/verticals/mainline/db/migrations --no-headers
```

Measured output of exactly that command:

```
lint: 261 file(s) checked in …/head261/verticals/mainline/db/migrations
lint: 7 finding(s)
```

All seven are `producer-absent`. No other rule fired.

---

## The seven, and where the chain would have stopped

| relation | first reference (where the chain halts) | sites |
|---|---|---|
| `mainline_ops.outbox` | `0101_fn_check_materialised.sql:91` | 2 |
| `mainline.identity_assignment` | `0140a_fn_cbm_account_guard.sql:248` | 1 |
| `mainline.patrol_run` | `0163_v_fixity_coverage.sql:96` | 1 |
| `mainline_meas.agent_action` | `0164_v_agent_actions.sql:88` | 3 |
| `mainline_meas.standing` | `0171_v_standing_components.sql:111` | 8 |
| `mainline_meas.person_measure_policy` | `0171_v_standing_components.sql:112` | 2 |
| `mainline_ops.site_register_signal` | `0198x_no_rls_on_cdc_sources.sql:106` | 1 |

Seven relations, eighteen reference sites, 261 files, 134 schema-qualified producers, 586
references. Every one of those numbers came out of the walk; none is asserted.

**`mainline_meas.person_measure_policy` is the one worth pausing on.** It never appeared in
any SQLSTATE, because CockroachDB reports the *first* absent relation in a statement and
`standing` is named one line earlier in both views that join it. A census built from
observed error codes could not have seen it. This rule reads files, so a shadowed gap is
not a special case — it is just another line.

---

## Why a *static, whole-tree* rule and not "did the file apply?"

Because the file that carries the defect is not the file that fails. Measured on the
local node (`cockroachdb/cockroach:v26.2.5`, database `w_w1`, created and dropped by the
run):

```
0101-shaped fn   OK
0121-shaped trg  REFUSED [42P01] relation "mainline_ops.outbox" does not exist
0099 producer    OK
0121 retried     OK
```

`CREATE FUNCTION` does not resolve table references inside a PL/pgSQL body, so
`0101_fn_check_materialised` — the file that actually names `mainline_ops.outbox` —
**applies clean**. `CREATE TRIGGER` does resolve them, so the refusal surfaces two dozen
files later, in a file that never mentions the missing table. A per-file check cannot
attribute that, and a dry run cannot see it before file 156.

The subtraction can, from the text, in under a second, with no server.

---

## Why the findings carry no SQLSTATE

Each entry in the artefact has `"sqlstate": null`, and the field is present rather than
omitted so that the absence is a stated fact.

Nothing was executed to produce this file. No server answered, no database was created, no
migration ran. That is the entire advantage of catching this class here instead of at file
156 of 261: by the time there is a SQLSTATE to quote, a deployment has already stopped
halfway through a forward-only chain, and every file below the halt is unapplied.

---

## What happened while this was being written

The same rule, the same command, over the working tree at the moment of capture:

```
lint: 271 file(s) checked in verticals\mainline\db\migrations
lint: no findings
```

Zero. W2–W5 landed their ten files during the capture, and the rule went from seven to
none. Both observations are in the artefact — `before` and `working_tree_at_capture` — and
neither is hidden behind the other. The green here is a live working tree, not a record
run; **W6 takes the record run through `trappoint migrate up`**, and that is the number
that counts.

---

## What the rule deliberately does not report

* **`trappoint.*`, `pg_catalog.*`, `information_schema.*`, `crdb_internal.*`,
  `system.*`.** `trappoint` is created by `trappoint migrate bootstrap` before the first
  migration runs; the other four are the engine's. None is ever produced by a migration.
  They are allowlisted by name, not by pattern — "looks like a catalog" is the kind of
  guess that later hides a real gap.
* **Anything a comment says.** References and producers are both read from
  comment-stripped SQL, so a `-- requires: mainline_ops.outbox` header creates no
  reference *and* a commented-out `CREATE TABLE` satisfies nothing.
* **Trees that declare no allocation.** Rule D runs where
  `<tree>.allocation.toml` exists, which is the same gate rule B already uses and for the
  same reason: such a tree has asserted that every number in it has an owner and that the
  directory is the whole of a deployable schema. A tree without one is a fragment.

That last exclusion has one live consequence, and it is recorded here rather than left to
be discovered:

> **`packages/trappoint-sql/refvertical/sql` has five dangling references of its own** —
> `trappoint_ref.clause`, `trappoint_ref.event`, `trappoint_ref.site`,
> `trappoint_ref.ledger_intake`, `trappoint_ref.event_severity_revision`. The reference
> vertical is a partial substrate binding that exists for `trappoint render --check` and
> never for a deployment, so this is not necessarily a defect there. It is not this
> wave's tree and not this worker's file, so it is reported and not touched.

---

## Regenerating

```python
from pathlib import Path
from trappoint_migrate.producers import census, census_payload

report = census(Path("verticals/mainline/db/migrations"))
payload = census_payload(report, relative_to=Path("."))
```

`packages/trappoint-migrate/tests/test_producers.py` keeps both ends honest:
`test_the_observed_red_is_recorded_and_names_exactly_the_seven` reads this artefact and
checks it still names the seven; `test_the_committed_tree_grows_no_eighth_gap` reads the
live tree and fails the day an **eighth** appears. The second is a ratchet rather than a
count — pinning `== 7` would turn every landed producer into a broken test, and a test a
worker has to edit to make progress is a test that gets edited until it says nothing.
