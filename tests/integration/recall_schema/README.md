<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# `tests/integration/recall_schema` — illegal histories against the recall band

Eight illegal histories and four unwelding cases, each asserting an **exact SQLSTATE** and an
**exact constraint or trigger name**. A test that asserts "an exception was raised" is worthless
for a product whose deliverable is a refusal: the diagnosis *is* the product.

Plus **RC-00**, which needs no cluster at all — see *The checks that need no cluster* below. It
exists because the machine this band was written on could not reach one, and a band that can only
be checked by a run that cannot happen is a band nobody has checked. It has already caught two
real defects.

## Running it

The suite needs a real CockroachDB **v26.2** and finds one in this order, skipping with a reason
if it cannot:

1. `MAINLINE_TEST_DSN` (or `COCKROACH_URL` / `CRDB_URL`) pointing at a running cluster;
2. a `cockroach` binary on `PATH` — an in-memory single node is started for the session;
3. a running Docker daemon — `cockroachdb/cockroach:latest-v26.2` is started and removed.

```bash
# whichever is available
docker run -d --rm --name crdb -p 26257:26257 \
  cockroachdb/cockroach:latest-v26.2 start-single-node --insecure --store=type=mem,size=2GiB
export MAINLINE_TEST_DSN='postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable'

pytest tests/integration/recall_schema -v          # everything
pytest tests/integration/recall_schema -m shape    # RC-00 only; no cluster needed
```

The session fixture creates a throwaway database, tries `feature.vector_index.enabled`, applies
`prereq/00_consumed_tables.sql` and then the **23 reserved recall migrations** — `0040–0046`,
`0080–0088`, `0112–0114`, `0136–0139` — forward from clean in one run, and drops the database
afterwards. Files are applied **one statement at a time** through a dollar-quote-aware splitter
(`_support.split_statements`), because on an autocommit connection a whole-file send is one
implicit transaction, and a multi-statement DDL transaction is not the same animal as a sequence
of schema changes — `CREATE TRIGGER` naming a function created in the same transaction is exactly
the shape that differs. The deployed runner applies one statement per file (§18); the suite must
not be more permissive than the thing it tests. `test_rc00c` proves the splitter never cuts a
`$$` body, on every file in the band.

The vector-index cluster setting is **attempted, not required**: if v26.2 has retired
`feature.vector_index.enabled` on the way to GA, an unknown-setting error must not turn into a
skip — that would report green-by-absence on precisely the cluster the band is meant to run on.
What actually decides the matter is whether 0041/0042 apply. The run prints which happened.

**A skipped run verifies nothing.** The skip message names which of the three routes is missing.
A Docker CLI on `PATH` with a dead daemon does not *fail* `docker info`, it **blocks**; the probe
is timeout-guarded so that situation skips in ten seconds instead of erroring the session.

## The checks that need no cluster (RC-00)

`test_rc00_migration_shape.py` reads the band as text. Four of its checks are hygiene — the file
set is complete and ordered, every file carries its REUSE headers and cites an invariant id
(§18's own CI rule), no `SERIAL` / `nextval` / `CREATE SEQUENCE` / standalone `CREATE VECTOR
INDEX` — and three are platform law, each of which was found by reading Cockroach Labs'
documentation rather than by running anything:

| Check | Rule | Why it is not style |
|---|---|---|
| `rc00e` | No `FOR … IN`, `FOREACH`, `PERFORM`, `EXECUTE`, `CASE`, `GET DIAGNOSTICS` in a trigger body | CockroachDB's PL/pgSQL does not implement any of them. §5.11's style rule is a capability list wearing a style rule's clothes |
| `rc00f` | Column reads are `(NEW).col`; only an assignment target is bare `NEW.col :=` | A **documented known limitation**: *OLD and NEW must be wrapped in parentheses when accessing column names*. The v26.2 Triggers page's own example reads `(NEW).wage` and assigns `NEW.wage := (NEW).wage + 5`. **ARCHITECTURE §5.11 is written in the unparenthesised PostgreSQL style throughout**, so this is a transcription trap the whole deployment walks into once per trigger |
| `rc00g` | A trigger function may only name columns the table it is welded to actually has | CockroachDB compiles PL/pgSQL through the optimizer with `NEW` bound to the trigger table's row type, so a reference in an unreachable branch is still plausibly resolved at `CREATE TRIGGER`. **Whether it actually is remains unverified** — which is the reason the code must not depend on the answer. This check is what stops the two cue projectors being helpfully merged back into one |

Both platform checks were made red before they were made green: reintroducing `NEW.event_id` in
0139 and a stray `NEW.severity_gate` in 0114 fails exactly `rc00f` and `rc00g`, naming the
offending function, column and weld.

## The cases

| Case | Illegal history | Asserts |
|---|---|---|
| **RC-01** | Insert an embedding whose `site_id` / `scope_id` / `facet` are forged | The row is **rewritten** from the parent cue; the forged tree is empty and the true tree returns the cue under the retriever's own arm shape |
| **RC-01b** | Insert a coarse row claiming `severity_gate = 0` for a fatality | Rewritten to 5 — the sweep's blocking rule is not writable |
| **RC-02** | Insert an embedding with no parent cue | `P0001` · *no parent cue — cannot place a vector in a prefix tree* · trigger `cue_prefix_project_embedding` |
| **RC-02b** | The same on the coarse sidecar | `P0001` · trigger `cue_prefix_project_coarse` (which calls `fn_cue_coarse_project` — see `rc00g`; the trigger names are the mechanism's public surface and are unchanged) |
| **RC-02c** | — | The `RAISE` beats the foreign key **deterministically**; the observable SQLSTATE is not a race |
| **RC-03** | Insert a `recall_candidate` claiming `severity = 1` for a severity-5 event | Rewritten to 5 |
| **RC-03b** | A candidate naming no event | `P0001` · *no such event — a recall candidate cannot be typed* · trigger `candidate_project` |
| **RC-04** | A run under an unanchored policy | `P0001` · trigger `recall_policy_anchored` |
| **RC-04b/c** | An anchor outside any cosigned checkpoint; an uncosigned checkpoint | `P0001` |
| **RC-05** | A run recognising a bonded fatality it did not make blocking | `23514` on `bonded_fatalities_all_blocking` |
| **RC-05b** | A bonded severity-5 blocking check lands | The **database** moves both counters, `(0,0) → (1,1)` |
| **RC-06** | A run whose candidates do not partition | `23514` on `candidates_conserved` |
| **RC-07** | `UPDATE` / `DELETE` on `silence_ledger` | `P0001` · *this table is append-only; write a new row* |
| **UW-01** | Drop `bonded_sev5`, then write the lying run row | **Still `23514`** — MI16 is depth 2 |
| **UW-02** | Drop `cue_prefix_project_embedding`, then forge a prefix | **Accepted** — the prefix weld is depth 1, and this test says so |
| **UW-03** | Drop `recall_policy_anchored` | Unanchored run accepted (depth 1); the `policy_version` FK residual still returns `23503` |
| **UW-04** | Drop `candidate_project` | Forged severity stands (depth 1); `candidate_sev_range` still refuses nonsense |

## Three honesty notes, because they change what the results mean

**The cluster-backed cases have not been run.** At the time of writing, the machine had no
`cockroach` binary and a stopped Docker daemon, and downloading one is not this worker's call to
make. RC-01…RC-07 and UW-01…UW-04 are therefore **written and collected but unexecuted**; they
skip with the reason above. Everything claimed about SQLSTATEs and constraint names in the table
below is a claim about what the code asserts, not a report of a run. RC-00 is the part that has
actually been executed, and it is red-before-green.


**`prereq/` is a fixture, not a migration.** The recall band consumes `mainline.event`,
`activity_node`, `blocking_check`, `ledger_checkpoint` and `cosignature`, all owned by other
workers and none of them yet in this repository. `prereq/00_consumed_tables.sql` supplies them —
`activity_node`, `event`, `ledger_checkpoint` and `cosignature` verbatim from ARCHITECTURE §5.4
and §5.6, `blocking_check` as a labelled **stub** carrying only the columns `fn_bonded_sev5`
reads. Every statement is `IF NOT EXISTS`, so once the real migrations land the fixture becomes
a no-op and the suite runs against the deployed shapes. **No MAINLINE enforcement lives in the
fixture**: nothing here can pass because of something `prereq/` did.

**RC-07 may be exercising a stand-in.** `fn_refuse_mutation` is §5.11 #9 and belongs to the
trigger band (`dm-functions-triggers`). The suite uses the deployed mechanism when it is
present; when it is absent it applies an identical-bodied stand-in from `prereq/90` and
`test_rc07c` prints which of the two ran. In stand-in mode RC-07 proves the recall band is
*compatible* with the append-only mechanism — not that the deployed schema carries it.
