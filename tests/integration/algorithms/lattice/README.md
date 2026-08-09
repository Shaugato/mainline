<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DELTALATTICE SQL suite — decision D8, executed

Owner: algorithms worker **W4 (`delta-lattice`)**. This suite covers the three migrations
this worker owns and nothing else in anybody's band:

| Migration | Object | Band |
|---|---|---|
| `0049a_delta_witness.sql` | `mainline.delta_witness` | `0049a–0049z`, the algorithms table annexe |
| `0140_fn_delta_witness_guard.sql` | `mainline.fn_delta_witness_guard()` | `0140–0144`, vertical functions |
| `0145_trg_delta_witness_guard.sql` | `z_delta_witness_required` on `mainline.clause_version` | `0145–0149`, vertical triggers |

They were authored as `0205` and `0211` under the `0200–0219` annexe that
`docs/leads/algorithms.md` D9/§9 reserved. **That annexe is revoked.** `ARCHITECTURE.md` §18
never defined a `0200+` space, `0200` and above is `UNALLOCATED` in
`verticals/mainline/db/migrations.allocation.toml`, and `trappoint migrate lint` rule B
refuses any file that claims it. `test_0049a_shape.py` reproduces rule B here and asserts
the absence from the other side.

## The claim this suite exists to execute

```sql
BEGIN;
  INSERT INTO mainline.delta_witness  (...);   -- every witness, FIRST
  INSERT INTO mainline.clause_version (...);   -- the version row, SECOND
COMMIT;
```

Skip the first statement on a `weaken`/`remove` with `delta_basis='lattice'` and the second
raises `P0001`:

```
MAINLINE: a lattice weakening must carry its minimal witness set
```

An unexplainable weakening verdict does not get to exist in this database. Not "is flagged",
not "is logged": **cannot be stored.**

## What runs where

| File | Needs a cluster? | What it proves |
|---|---|---|
| `test_0049a_shape.py` | no | One statement; the four linted header keys; the filename convention; the file resolved against `migrations.allocation.toml` and its `mode` compared with the file's own banner (lint rule B); and — the one that earns the file — the nine literals in `rule_id_closed` held equal to `mainline_domain.contracts.RULE_IDS`. |
| `test_guard_shape.py` | no | The `0211` split held: one statement each, function in the function band, trigger in the trigger band, `0049a < 0140 < 0145`. The two P0001 strings, verbatim. Decision D10, read out of the function body: the guard reads only columns the INSERT supplies. The exemption scoping (`abstain_to_weaken` and `human` out, `lattice+model` in) that is P7 at this gate. |
| `test_witness_or_refuse.py` | **yes** | The exit criterion. The refusal, its exact message and SQLSTATE; the same INSERT succeeding with witnesses first; the second refusal for a witness set with no minimal member; and the honest limits — a fabricated witness satisfies the guard, and the trigger can be disabled. |
| `test_verdict_round_trip.py` | **yes** | The seam nothing else covers: a verdict `mainline_domain.lattice.explain` actually computed, written through the guard, one edit per rule. A `rule_id` the Python side emits and the `CHECK` does not admit is `23514` on every weakening — which the guard then reports as *no witnesses at all*, indistinguishable in a console from a lattice that found nothing. |

## The red half is a fixture, not a story

PL-2: for a product whose deliverable is a refusal, a suite that has never been red asserts
nothing — and a suite that was red for the *wrong* reason is worse, because it is
green-looking evidence of a mechanism that is not there. "The INSERT was refused" is equally
consistent with a `NOT NULL`, a foreign key, or a typo in the test's own SQL.

So `conftest.py` builds **two** schemas from the same file list:

* `guarded_schema` — spine + `0049a` + `0140` + `0145`;
* `unguarded_schema` — the identical stack **minus `0145`**, so the function exists and
  nothing calls it.

`test_the_refused_insert_is_accepted_when_0145_is_withheld` runs the identical INSERT against
the second one and asserts it lands. The difference between the two schemas is exactly one
migration, and that migration is the mechanism.

## Getting a cluster

The suite looks in this order and **skips with the reason** if it finds nothing:

1. `MAINLINE_TEST_DSN` (or `COCKROACH_URL` / `CRDB_URL`);
2. a `cockroach` binary on `PATH` → an in-memory single node for the session;
3. a running Docker daemon → `cockroachdb/cockroach:latest-v26.2`.

```
MAINLINE_TEST_DSN=postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable \
  pytest tests/integration/algorithms/lattice -q
```

A skipped run verifies nothing and the skip message says so. AWS credentials are not valid on
the build machine and CockroachDB Cloud is not assumed; a local binary or a container is the
intended path.

**Executed 2026-08-08 against CockroachDB CCL v26.2.5**: 65 passed, no skips.

## No stand-in spine, deliberately

The neighbouring DIRECTRIX suite ships `prereq/00_spine_tables.sql` because the schema lead's
migrations had not landed when it was written. They have landed. A stand-in here would be
strictly worse than nothing: the entire claim is that a **real** `mainline.clause_version`
insert is refused by a **real** trigger, and a hand-written table with the same column names
would prove that the test file is self-consistent and nothing else.

`_lattice_sql_support.spine_migrations()` resolves the prerequisites **by content** —
`CREATE SCHEMA mainline`, `CREATE TYPE mainline.control_delta`, and the four tables — so a
renumber inside the schema lead's bands does not silently reduce this suite to a skip. If an
object is genuinely missing it raises and names it.

## Two measured platform details

* **A `23514` on CockroachDB v26.2.5 names the CHECK expression, not the constraint.**
  `failed to satisfy CHECK constraint (note != '':::STRING)`, where PostgreSQL would name
  `note_stated`. Every refusal exhibit that promises an operator a constraint name for a
  `23514` has to supply the name itself. The `P0001` messages are ours and arrive verbatim.
* **The composite FK the design asks for is unbuildable.**
  `FOREIGN KEY (clause_uuid, commit_id) REFERENCES mainline.clause_version` is directly
  incompatible with the ordering contract, because CockroachDB checks foreign keys per
  statement and does not implement `DEFERRABLE` / `INITIALLY DEFERRED` — so the *first*
  statement of the transaction would be refused with `23503` for pointing at a row the second
  statement has not written yet. `0049a`'s header records this and
  `test_the_absent_composite_fk_is_explained_rather_than_omitted` keeps the record honest.

## Why `_lattice_sql_support.py` and not `_support.py`

`tests/integration/recall_schema/_support.py` and
`tests/integration/algorithms/candidates/_support.py` both already exist. pytest's prepend
import mode puts both directories on `sys.path`, so two modules named `_support` resolve to
whichever collection reached first — a silent failure that produces a suite exercising
somebody else's helpers. Same reason `tests/unit/domain/lattice/_lattice_fixtures.py` is not
`_fixtures.py`, and the round-trip suite builds its own CATs rather than importing that
module: a suite whose fixtures appear and vanish depending on what else was selected is a
suite that is red for reasons nobody can reproduce.

## What this suite does not claim

The guard makes a weakening carry **an** explanation. It cannot make the explanation **true** —
`test_a_fabricated_witness_satisfies_the_guard` demonstrates exactly that rather than leaving
it for a reviewer to find. Nor does it stop a writer declaring `restate` on an edit that is
really a weakening; that dodge is closed, if it is closed, by the matcher and the
CONSERVATION OF BLAME MASS ledger (workers W8/W9) accounting for every blood-written
obligation across the commit independently. And the merge refusal itself is the kernel lead's
`gate_closed_when_issued` / `cr_gate_closed_when_merged`, not this worker's. D8 closes one
hole and names the others.
