<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# VERIFY (demo) — check the film without taking our word for any of it

The repository root carries [`VERIFY.md`](../../../VERIFY.md), which is about the *product*.
This file is about the *three minutes of video*: for each load-bearing claim in the film, the
cheapest way for a stranger to reproduce it, ordered by how much they have to accept on faith.

**Lead with Tier 2.** It needs no credential of ours, no cloud account, and no model call.

| Tier | Credential | Reproduces | Time |
|---|---|---|---|
| **1 · the bundle** | none | the custody chain behind the on-camera ledger leaf, and that the exhibited refusal is in the ledger | ~30 s |
| **2 · your laptop** | none | **the merge refusal itself**, byte-for-byte the same SQLSTATE and the same exhibit name | ~4 min |
| **3 · your own agent** | a published, scoped key on a throwaway cluster | the audit surface, the vector-index proof and the silence ledger, over CockroachDB's own managed endpoint with none of our code in the path | ~2 min |

---

## Tier 1 — the offline bundle verifier

```bash
git clone https://github.com/Shaugato/mainline && cd mainline
pipx install ./packages/trappoint-verify
trappoint-verify --bundle evidence/demo-run-<ts>/bundle.json
```

Installed from the clone, not from an index: **this package is not published to PyPI**, so
`pipx run trappoint-verify` would resolve to nothing. Saying so costs one line and saves a judge
the two minutes of assuming the tool is missing.

Its only dependency is a cryptography library; the canonicaliser is vendored so that stays true.
It checks the signed checkpoint chain, the inclusion and consistency proofs, and that the
refusal exhibited on camera is present in the ledger under the leaf the film showed.

What it does **not** do is tell you the narrative was true. It tells you the record is
internally consistent and has not been edited since it was signed.

---

## Tier 2 — reproduce the refusal on your own machine

This is the strongest single claim available and the fixture design makes it free.

```bash
git clone https://github.com/Shaugato/mainline && cd mainline
just corpus:up          # single-node cockroachdb in docker
just corpus:seed        # migrations + committed fixtures, embeddings included
just demo:beats         # replays the on-camera beats locally
```

You should see the same exhibit the film shows: the merge is refused, the SQLSTATE is a check
violation, and the constraint name is `gate_closed_when_issued`. Then do the interesting part
yourself — connect as `root`, bypass every line of our application code, and try it by hand:

```sql
UPDATE mainline.permit SET state = 'merged' WHERE external_ref = 'WO-88213';
DELETE FROM mainline.blocking_check WHERE permit_id = (
  SELECT permit_id FROM mainline.permit WHERE external_ref = 'WO-88213');
```

Both are refused. The exact strings, with the migration file and line each one is defined on,
are in [`REFUSAL-STRINGS.yaml`](REFUSAL-STRINGS.yaml) — so you can check that what the film
showed is what the schema says, without replaying the video frame by frame.

Then run the third statement from the bypass beat:

```sql
ALTER TABLE mainline.permit DROP CONSTRAINT gate_closed_when_issued;
```

**It succeeds**, on your machine as on ours. That is the point of filming it. A cluster
administrator can remove the gate; what they cannot do is remove it unobserved, because the
custodian patrol writes an attested leaf naming the change. **The claim is tamper-evidence and
it is never tamper-proofing.** Re-run the patrol and read the leaf.

And run the half that proves the other half means something — the unwelding matrix, where the
gate is removed one mechanism at a time and the histories that must still be refused are
asserted to be refused, and the ones that must now be admitted are asserted to be admitted:

```bash
just conform
```

A suite in which nothing is ever admitted proves only that the database is broken.

---

## Tier 3 — point your own agent at a cluster we do not control

```bash
claude mcp add mainline-verify https://cockroachlabs.cloud/mcp --transport http \
  --header "mcp-cluster-id: <cluster-id>" \
  --header "Authorization: Bearer <service-account-api-key>"
```

The cluster id and key are published beside the submission for the duration of judging.

### Why this is safe, stated rather than assumed

The managed MCP server requires the service account to hold a cluster-level role, and although
the write surface is insert-only it is **real**. So:

1. **The published key is on a separate throwaway cluster named `mainline-verify`**, restored
   nightly from the demo cluster. It holds **synthetic data only** — a fictional operator,
   fictional people, fictional incidents.
2. **No key is ever published on the demo cluster.** Not a weaker key; none.
3. **The write surface is insert-only and bound to one table**,
   `mainline_meas.external_attestation`, which exists so that *your* agent can record the
   outcome of *its own* verification into our log. A third party's claim about our log is a
   different object from our claim about the world, and only the first one is something we
   should be able to accept.
4. **The key is revoked when judging closes.**
5. Whether publishing a service-account key to anonymous verifiers is within Cockroach Labs'
   terms is a day-1 check. **If the answer is no, this tier degrades to a recorded MCP session
   plus our own read-only aggregate endpoints, and this file says so on the day rather than
   quietly dropping the tier.**

### The design constraint these prompts are shaped around

The managed surface is read-only by default, one statement per call, at most 16 384 characters
per statement, a 20-second timeout, a **10 KiB response cap that is not raisable**, a 25-row
default on `SELECT`, and no reachability into `system`, `crdb_internal`, `pg_catalog`,
`information_schema` or `pg_extension`.

The response cap is the binding one. **Every question below is therefore aggregate-first by
construction and every view it touches is purpose-built to fit** — none of them depends on a
system catalog, and each is shaped to at most 25 rows. That is a functional requirement of the
product surface, not an operational detail, and a nightly test asserts it.

### The three prompts used on camera

Paste them as they are. Each is backed by one purpose-built view.

**1 · "Are dispositions keeping up with what was surfaced? Show orphans and the worst ancestor
severity per site and quarter."**

```sql
SELECT site_id, q, surfaced, dispositioned, orphans,
       worst_ancestor, worst_severity, ancestry_complete, rows_complete
  FROM mainline_audit.v_disposition_coverage
 ORDER BY orphans DESC, q DESC
 LIMIT 25;
```

`ancestry_complete` is not decoration. When it is false, the counts beneath it are **lower
bounds** — the ancestry walk was truncated and the view says so instead of rounding the problem
away. `rows_complete` says whether the 25-row window covered every group; a view that silently
truncated an aggregate would be a safety defect in this product.

**2 · "Prove the vector search actually used an index. Show me the plan."**

```sql
EXPLAIN
SELECT c.cue_id
  FROM mainline.event_cue_embedding@cue_scoped_idx AS c
 WHERE c.site_id = $1 AND c.scope_id = $2 AND c.facet = $3
 ORDER BY c.emb <=> $4
 LIMIT 10;
```

Read the plan for a `vector search` node on `cue_scoped_idx` with a **non-empty** `prefix
spans:` line. Two things about that query are deliberate and neither is cosmetic:

- **Every prefix column is constrained to a single value.** A prefix constrained with `IN (...)`
  does not qualify, which is why an ancestry walk is one such query per ancestor, unioned and
  re-ranked, rather than one query with a list.
- **The index is named explicitly.** At demo corpus scale the optimizer does *not* choose the
  vector index on its own — the plan becomes top-k, render, filter, scan. That is a measured
  result recorded in the ground-truth attestation, not a workaround: a plan that flips on table
  statistics has no business sitting beneath a safety gate, so every retrieval arm pins its
  index and the assertion in CI asserts traversal of the **named** index.

One practical note, because you will hit it: `$4` is a 1024-dimension vector, and a literal at
full float precision crowds the 16 384-character statement cap. Print it at six significant
figures — that lands around 10 KB and leaves room — or run the same shape against the
256-dimension coarse sidecar `mainline.event_cue_coarse@cue_sweep_idx`, whose literal is a
quarter the size and whose plan shows the same two properties.

**3 · "What did you decline to surface, and with what arithmetic?"**

```sql
SELECT site_id, source, reason, severity, n,
       mean_score, mean_threshold, nearest_miss
  FROM mainline_audit.v_silence_summary
 ORDER BY severity DESC, n DESC
 LIMIT 25;
```

`nearest_miss` is the column that earns this view: the highest score that still fell under
threshold is the closest the system came to speaking. A band whose nearest miss sits a
thousandth under its threshold is a calibration finding, not a clean report — and a system that
cannot answer this question at all is not answering it favourably, it is just not answering it.

### Now try to break it — the negatives matter more than the positives

Every one of these must **fail**:

```sql
SELECT count(*) FROM mainline_qa.v_disposition_profile;   -- must fail, on every tier, forever
SELECT count(*) FROM crdb_internal.jobs;                  -- must fail
SELECT count(*) FROM pg_catalog.pg_class;                 -- must fail
SELECT count(*) FROM information_schema.tables;           -- must fail
```

…and an `insert_rows` into anything other than `mainline_meas.external_attestation` must be
rejected. The per-person deliberation measurement lives in `mainline_qa`, which **no MCP service
account ever receives, on any tier**, and every read of it writes a record that it was read.

That `crdb_internal` is unreachable is not an inconvenience we worked around. It is what proves
the audit views **are** the API rather than a bypass around one.

---

## What the film shows that none of these tiers can check

The honest complement to the list above, kept here so it travels with it:

- **Nothing here separates a considered disposition from a rubber stamp.** See
  [`DEMO-HONESTY.md`](DEMO-HONESTY.md) §5 for what the system does instead, and why we would
  rather say this out loud than be asked.
- The corpus is **synthetic**, so the gold set bounds our own linker from above and does not
  measure real-world precision.
- Every date in the ancestry walk is a **column value in the commit DAG**. `AS OF SYSTEM TIME` is
  not used to produce any frame of the film, and the measured garbage-collection window on this
  cluster is a small number of minutes — which the generated honesty card prints, in minutes,
  rather than leaving you to take on trust.
- The database is in Singapore and Bedrock inference is in Sydney. **A claim of end-to-end
  Australian data residency would be false for this deployment**, so it appears nowhere.

---

## If something here does not reproduce

That is a defect and we would like to know. The suites behind this document:

- `tests/integration/corpus/` — the seeded database matches the lock, and the projected counters
  equal an independent re-derive;
- `packages/trappoint-conformance/` — the illegal histories, and the unwelding matrix;
- `tests/integration/mcp/` — the audit surface measured against the live endpoint, and every
  negative above asserted, deliberately bypassing our own client-side screen. A control that
  lives only in our client is a control an attacker skips by not using our client.
