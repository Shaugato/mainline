<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# F03 — "the vector index is not chosen by the planner"

> ## STATUS: **STRUCK.** This is not a finding. It is the record of a claim we withdrew.
>
> It carries an `F03` number because that is the slot it was assigned before it was checked.
> **It must not appear in the findings list of `docs/upstream/COCKROACHDB-FIELD-NOTES.md`.**
> Its home is `docs/upstream/STRIKE-LEDGER.md`. See §7 for the documents that still carry the
> withdrawn claim, two of them judge-facing, none of them this file's to edit.

---

## 1 · What happened

Early in the build we wrote down that CockroachDB would not use one of our search indexes
unless we named it in the query. We tried twice to show that again — once on the cloud database
four days later, once on a local machine today — and both times the database used the index
without being asked, so we are taking the claim back.

---

## 2 · The words in that claim, in plain language

Every term the rest of this file leans on is defined here first.

| Word | What it means here |
|---|---|
| **index** | A second copy of some of a table's data, arranged so a particular question can be answered without reading the whole table. |
| **vector index** | An index built for "find me the rows most similar to this one" rather than "find me the row with this id". The similarity is between long lists of numbers that stand for meaning. CockroachDB's is called C-SPANN. |
| **ANN** | *Approximate nearest neighbour* — the search a vector index performs. "Approximate" because it is allowed to miss a near-miss in exchange for being fast. |
| **prefix-constrained** | Our vector index has two ordinary columns in front of the vector one. "Prefix-constrained" means the query pins both of those to a single value each, so the search happens inside one small neighbourhood instead of the whole table. |
| **query plan** | The database's written-out decision about *how* it will answer a question — which indexes it will read, in what order. You ask for it with the word `EXPLAIN` in front of your query. |
| **planner**, or **optimizer** | Two names for the same thing: the part of the database that writes the plan. It is *cost-based* — it estimates the work each option would take and picks the cheapest. That estimate depends on how many rows it thinks are in the table, which is why a plan can change as a table grows. Our own older notes say "optimizer"; this file says "planner" except when quoting them. |
| **hint** | Writing `FROM table@index_name` instead of `FROM table` — telling the planner which index you want. It is a preference expressed to the planner, not an instruction to the storage layer. |
| **SQLSTATE** | The five-character code the database returns with an error. Same code, same meaning, every time — which is why we quote codes rather than error text. |
| **scratch database** | A database created for one test run and dropped when it ends. Ours are named `upstream_f03_` followed by eight random characters. |
| **tier** | Which product you are running on. CockroachDB Cloud **Basic** is the free one. A **local single-node** cluster is one copy of the database running on one machine. These are different exams and a result on one is not a result on the other. |

---

## 3 · What we originally claimed, and where we wrote it

`docs/adr/0002-g1-platform-ground-truth.md`, row **GT-06**, dated **2026-08-07**, measured on
**CockroachDB Cloud Basic, `aws-ap-southeast-1`, CockroachDB CCL v26.2.5**:

> At 5,200 rows the optimizer does not choose the vector index. The unhinted plan filters
> *after* scanning. The index is traversed only when named explicitly (`FROM tbl@idx_name`).
> — `docs/adr/0002-g1-platform-ground-truth.md:36`

The companion row **GT-06b** recorded that naming the index made it traverse.

**That row has no captured transcript.** The ADR records the conclusion; no `EXPLAIN` output
from 2026-08-07 was saved anywhere in this repository. We searched for one before writing this
file. That absence is the whole reason the claim could survive for ten days.

---

## 4 · The three exams, and what each one said

**These are three separate exams. A result from one is never reported as a result from another.**

| # | Exam | Date | Label | What it says |
|---|---|---|---|---|
| A | Cloud Basic, `aws-ap-southeast-1`, v26.2.5 | 2026-08-07 | **ORIGINAL NOTE — no transcript, cannot be checked** | index not used unhinted at ~5,200 rows |
| B | Cloud Basic, `aws-ap-southeast-1`, v26.2.5 | 2026-08-11 | **ARCHIVED-EVIDENCE — not re-run today** | index used unhinted at 0, 200, 1,100 and 5,300 rows |
| C | Local single-node CCL v26.2.5, user `root` | **2026-08-17** | **RE-RUN TODAY — the claim did not survive it** | index used unhinted at 0, 200, 1,100 and 5,300 rows |

### 4.1 · Exam B — Cloud Basic, archived, deliberately not re-run

**Artefact:** `evidence/aws/ann/explain-unhinted.txt`, captured **2026-08-11T04:07:47Z**; the
row-count sweep inside it ran **2026-08-11T02:25:36Z**. Companion machine-readable record:
`evidence/aws/ann/ann-proof.json`, same timestamp.

**It was not re-run today, on purpose.** Re-running it would mean driving several thousand
inserts and a corpus rebuild against a shared live cluster that other things depend on. The
artefact is cited by path and timestamp instead.

The artefact reaches the conclusion in its own words, and it reached it before this document
existed:

```
     rows  hinted traverses ce_ann   unhinted traverses ce_ann
  -------  ------------------------  --------------------------
        0  True                      True
      200  True                      True
     1100  True                      True
     5300  True                      True

  unhinted NEVER stopped using ce_ann at any size swept
  GT-06 reproduces: False
```
— `evidence/aws/ann/explain-unhinted.txt`, Appendix A

`evidence/aws/ann/ann-proof.json` carries the same sentence in its `caveats` list:
*"THE GT-06 COUNTERFACTUAL DID NOT REPRODUCE."*

### 4.2 · Exam C — local single-node, re-run today

Run by `scripts/upstream/repro_vector_and_catalogue.py` on **2026-08-17** against
`CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)`, in a
scratch database the script created and then dropped. Full transcript:
`evidence/upstream/F03-vector-index-not-chosen.json`.

The scratch database gets a fresh random name on every run, so this document does not quote one.
The transcript records the exact name of the run that wrote it, under `exam.scratch_database`
and again under `teardown` (`created`, `dropped`, `confirmed_absent`), together with that run's
`started_at`. Re-running the script rewrites the transcript and leaves this document correct.

The table is the same shape as the real one
(`verticals/mainline/db/migrations/0031_clause_embedding.sql`): two ordinary columns then a
1,024-number vector column, with the vector index over all three. The vectors are seeded
pseudo-random unit vectors, not real embeddings. Statistics were refreshed with `ANALYZE`
before every measurement, so "the planner had stale row counts" is excluded as an explanation.

| rows in table | rows matching both prefix columns | unhinted used the index | hinted used the index | plan contained a full scan | plans byte-identical |
|---|---|---|---|---|---|
| 0 | 0 | **yes** | yes | no | **yes** |
| 200 | 67 | **yes** | yes | no | **yes** |
| 1,100 | 367 | **yes** | yes | no | **yes** |
| **5,300** | 1,767 | **yes** | yes | no | **yes** |

`5,300` is above GT-06's own `5,200`.

The last column is the sharpest part of the result. At every row count the two plans were not
merely equivalent — they were **the same bytes**. Their SHA-256 digests, recorded in the
transcript:

```
rows      0   unhinted d2e3e06860d0ba99…fee4d   hinted d2e3e06860d0ba99…fee4d
rows    200   unhinted 0f56d3a4f8de4e0d…69ca   hinted 0f56d3a4f8de4e0d…69ca
rows  1,100   unhinted 0f56d3a4f8de4e0d…69ca   hinted 0f56d3a4f8de4e0d…69ca
rows  5,300   unhinted 0f56d3a4f8de4e0d…69ca   hinted 0f56d3a4f8de4e0d…69ca
```

The plan itself, at 5,300 rows, without the hint:

```
distribution: local

• top-k
│ estimated row count: 10
│ order: +dist
│ k: 10
│
└── • render
    │
    └── • lookup join
        │ table: t_clause_embedding@t_clause_embedding_pk
        │ equality: (clause_uuid, commit_id) = (clause_uuid, commit_id)
        │ equality cols are key
        │
        └── • vector search
              table: t_clause_embedding@t_ann
              target count: 10
              prefix spans: [/'5b144fe2-…'/'/mill' - /'5b144fe2-…'/'/mill']
```

`• vector search` is the vector index being descended. `t_clause_embedding@t_ann` names the
index. `prefix spans` shows both leading columns pinned to one value each. No hint was given.

**Reproduce it:**

```
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe \
  scripts/upstream/repro_vector_and_catalogue.py
```

It creates one scratch database, prints its name, and drops it in a `finally:` block whether or
not anything failed. It touches nothing on CockroachDB Cloud and nothing named `mainline_demo`.

---

## 5 · Where we were wrong

**Almost everywhere, and it was our own process that let it stand.**

1. **We recorded a conclusion without recording the evidence.** GT-06 has no saved `EXPLAIN`
   output. A plan is cheap to capture and we did not capture it. Everything downstream of that
   one omission — a design decision, an automated check, two published tables — inherited a
   sentence nobody could check.
2. **We inherited it instead of re-deriving it.** GT-06 was quoted into `docs/leads/agents-mcp.md`,
   `docs/leads/algorithms.md` and `docs/HONESTY.md` as settled fact.
3. **We were slow to act on our own refutation.** The 2026-08-11 artefact stated plainly that
   GT-06 did not reproduce, and it correctly said correcting the ADR was not its file to edit.
   Six days later the withdrawn claim was still in `README.md`. Writing the correction down is
   not the same as landing it, and we treated it as if it were.
4. **We may still be wrong in the other direction.** We cannot say GT-06 was *false*. We can say
   it did not reproduce under two later sets of conditions. The 2026-08-07 run's prefix
   cardinality, vector distribution and statistics freshness were never recorded, so the honest
   statement is **"did not reproduce"**, never **"was wrong"**.

---

## 6 · What did hold, and what it means for the design

Two things survived, and they matter more than the claim that did not.

**The prefix rule is enforced by the server.** Keep the index named and remove *one* of the two
leading columns from the `WHERE` clause, and CockroachDB does not fall back to a slower plan —
it refuses the query outright. Measured today, local single-node v26.2.5:

```
EXPLAIN SELECT clause_uuid FROM t_clause_embedding@t_ann
 WHERE activity_root = $1 ORDER BY embedding <=> $2 LIMIT 10

  SQLSTATE 42809 · index "t_ann" cannot be used for this query
```

The same refusal, same code, is in the archived Cloud artefact twice
(`evidence/aws/ann/explain-unhinted.txt`, Appendix B). **This is a compliment, not a complaint,
and it belongs in `docs/upstream/WHAT-WORKED.md` rather than here.** A rule the server enforces
cannot rot the way a rule enforced by a comment in a migration file does.

**The decision GT-06 justified is still right, for a different reason.** Our system's whole claim
is that it behaves the same way every time. A plan the planner picks by estimating cost can
change when the table grows, when statistics go stale, or — on the evidence of our own two Cloud
measurements four days apart — for reasons nobody wrote down. Naming the index removes the way
the plan could change quietly. So our search queries keep naming it. What we can no longer say is
that naming it was **necessary** at this size. On both exams we can check, it was not: it
produced a byte-identical plan.

---

## 7 · Four documents in this repository still carry the withdrawn claim

Flagged, not fixed — this wave's rules put those files under other owners, and editing them from
here would collide.

| File | Line | What it still says |
|---|---|---|
| `README.md` | 220 | *"At 5,200 rows, unless the index is named in the statement, the database scans and then filters"* — and cites `evidence/aws/ann/explain-unhinted.txt`, the artefact that refutes it |
| `docs/submission/readme-parts/05-findings.md` | 27 | the same row, same citation |
| `verticals/mainline/demo/honesty/fixtures/g1-attestation.fixture.json` | 45 | *"index NOT used at 5200 rows; plan is top-k, render, filter, scan"* |
| `docs/adr/0002-g1-platform-ground-truth.md` | 20, 36 | GT-06 itself, uncorrected |

**The first two are judge-facing.** A reviewer who opens the cited artefact reads a claim in the
document and its refutation in the evidence it points at. That is worse than having no finding.

---

## 8 · Provenance

| | |
|---|---|
| **Finding label** | **STRUCK** |
| **Version** | CockroachDB CCL v26.2.5 (built 2026/07/28 18:56:00) — on all three exams |
| **Exam A** | Cloud Basic, `aws-ap-southeast-1`, 2026-08-07 — original note, no transcript |
| **Exam B** | Cloud Basic, `aws-ap-southeast-1`, 2026-08-11 — **ARCHIVED-EVIDENCE**, not re-run today |
| **Exam C** | local single-node CCL, 2026-08-17 — **re-run today**, claim did not survive |
| **Reproduction** | `scripts/upstream/repro_vector_and_catalogue.py` |
| **Transcript** | `evidence/upstream/F03-vector-index-not-chosen.json` |
| **Archived artefacts** | `evidence/aws/ann/explain-unhinted.txt`, `evidence/aws/ann/explain-hinted.txt`, `evidence/aws/ann/ann-proof.json` |
| **Nothing live was touched** | no CockroachDB Cloud query, no `mainline_demo`, no AWS call, no `GRANT`, `REVOKE`, `CONFIGURE ZONE` or cluster setting |

---

## 9 · What better would look like

**One concrete, implementable change: let `EXPLAIN` emit a plan identity that can be stored in a
document and checked later without the database that produced it.**

CockroachDB already computes something very close — the *plan gist*, a short string standing for
a plan's shape. The gap is at the other end. The function that turns a gist back into a readable
plan lives in the *catalogue* — the database's own bookkeeping, its tables about itself — and on
v26.2.5 that part of the catalogue is closed by default. That closure is finding **F04**. Both
halves, measured in one session today on the local single-node cluster:

```
EXPLAIN (GIST) SELECT 1
  -> AgICAgYC                                    answered

SELECT crdb_internal.decode_plan_gist('AgICAgYC')
  -> 42501 · Access to crdb_internal and system is restricted. HINT: …
```

So the compact, quotable form exists and the way to read it back does not — same user, same
session, same default settings. Recorded in this finding's transcript under
`plan_gist_round_trip`.

If `EXPLAIN (GIST)` had been quotable *and* readable back through a supported surface, GT-06
would have been one line in an architecture document that a later run could compare itself
against automatically — and this strike would have been a two-minute correction on 2026-08-11
rather than a ten-day-old sentence in a public README.

Everything else here is our failure, not the database's, and §5 says so.
