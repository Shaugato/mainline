<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# `tests/integration/recall_schema` — illegal histories against the recall band

Eight illegal histories and four unwelding cases, each asserting an **exact SQLSTATE** and an
**exact constraint or trigger name**. A test that asserts "an exception was raised" is worthless
for a product whose deliverable is a refusal: the diagnosis *is* the product.

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

pytest tests/integration/recall_schema -v
```

The session fixture creates a throwaway database, sets `feature.vector_index.enabled`, applies
`prereq/00_consumed_tables.sql` and then the **23 reserved recall migrations** — `0040–0046`,
`0080–0088`, `0112–0114`, `0136–0139` — forward from clean in one run, and drops the database
afterwards. Migration files are sent whole rather than split on `;`, because a client-side
splitter has to parse `$$` bodies and one that gets it wrong applies half a trigger.

**A skipped run verifies nothing.** The skip message names which of the three routes is missing.

## The cases

| Case | Illegal history | Asserts |
|---|---|---|
| **RC-01** | Insert an embedding whose `site_id` / `scope_id` / `facet` are forged | The row is **rewritten** from the parent cue; the forged tree is empty and the true tree returns the cue under the retriever's own arm shape |
| **RC-01b** | Insert a coarse row claiming `severity_gate = 0` for a fatality | Rewritten to 5 — the sweep's blocking rule is not writable |
| **RC-02** | Insert an embedding with no parent cue | `P0001` · *no parent cue — cannot place a vector in a prefix tree* · trigger `cue_prefix_project_embedding` |
| **RC-02b** | The same on the coarse sidecar | `P0001` · trigger `cue_prefix_project_coarse` |
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

## Two honesty notes, because they change what the results mean

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
