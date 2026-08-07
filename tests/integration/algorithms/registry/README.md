<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DIRECTRIX integration suite — migration 0207 and the SQL clause source

Owner: algorithms worker **W2 (`quantity-directrix`)**. Migration band `0200–0219`;
this worker owns `0207` and nothing else in it.

## What runs where

| File | Needs a cluster? | What it proves |
|---|---|---|
| `test_0207_shape.py` | no | The migration is one statement, cites its invariants, claims no refusal it does not implement, and — the one that earns the file — its `split_part` string literals still match the clause grammar in `mainline_domain.registry.encoding`. |
| `test_0207_view.py` | yes | `CREATE VIEW mainline.v_safe_direction_current` applies forward from clean on CockroachDB v26.2, returns the seeded parameters, and `mainline_domain.registry.sql` reads the same document out of the same tables and agrees with the pure-Python registry. |

`test_0207_shape.py` exists because the alternative is a worker whose only
verification is a skip. The cross-language check it performs cannot be done from
either side alone: the view searches the clause text for the literal
`'Direction: '`, that literal is defined in Python, and nothing in SQL knows it.
Change the grammar and the view keeps applying, keeps returning rows, and
silently reports every parameter as the empty string with `answers = false` —
which reads, in the console, exactly like a site that has ratified nothing.

## Getting a cluster

The suite looks in this order and **skips with the reason** if it finds nothing:

1. `MAINLINE_TEST_DSN` (or `COCKROACH_URL` / `CRDB_URL`);
2. a `cockroach` binary on `PATH` → an in-memory single node for the session;
3. a running Docker daemon → `cockroachdb/cockroach:latest-v26.2`.

```
MAINLINE_TEST_DSN=postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable \
  pytest tests/integration/algorithms/registry -q
```

A skipped run verifies nothing and the skip message says so. AWS credentials are
not valid on the build machine and CockroachDB Cloud is not assumed; a local
binary or a container is the intended path.

## The stand-in spine, and why the report names it

Migration 0207 is a view over `mainline.commit_obj`, `doc`, `clause` and
`clause_version`, all of which belong to the schema/kernel lead in band
`0001–0171`. At the time this suite was written those migrations had not landed,
so `prereq/00_spine_tables.sql` provides the columns 0207 reads, transcribed from
`ARCHITECTURE.md` §5.2 and §5.3.

`_directrix_support.spine_migrations()` looks for the real migrations **first**,
matching on content rather than on a guessed migration number, and the session
header prints which one was used:

```
[directrix] spine:    STAND-IN (schema lead migrations not landed)
```

A green run against a stand-in is a weaker claim than a green run against the
deployed schema. The report says which happened rather than leaving a reader to
assume the stronger one.

`prereq/00_spine_tables.sql` is **not a migration and must never become one.**

## Why `_directrix_support.py` and not `_support.py`

`tests/integration/recall_schema/_support.py` already exists. pytest's prepend
import mode puts both directories on `sys.path`, so two modules named `_support`
resolve to whichever collection reached first — a silent failure that produces a
suite testing somebody else's helpers.

## The negative assertion

`test_there_is_no_safe_direction_table` fails if `mainline.safe_direction` ever
appears. That is the mechanism, asserted from the other side: two columns in a
table are one `UPDATE` away from inverting every setpoint verdict in the system,
with no commit, no signature, no blame edge and no refusal. The registry is a
document in the gated commit DAG or DIRECTRIX does not exist.
