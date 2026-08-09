<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2

GENERATED FILE — do not edit by hand.

    python verticals/mainline/demo/judge/cli.py render          # rewrite this page
    python verticals/mainline/demo/judge/cli.py render --check  # fail if it has drifted

The source is QUESTIONS.yaml in this directory. Editing this page instead of that one
puts the prompt a judge reads outside the reach of the validator, which is the exact
failure this pack exists to prevent.
-->

# The judge pack — Tier 3, over CockroachDB's own managed endpoint

Every question below runs against the `mainline-verify` cluster over
`https://cockroachlabs.cloud/mcp`, with **none of our code between the prompt and the
row**. Point your own MCP client at it:

```bash
claude mcp add mainline-verify https://cockroachlabs.cloud/mcp --transport http \
  --header "mcp-cluster-id: <cluster-id>" \
  --header "Authorization: Bearer <service-account-api-key>"
```

The cluster id and key are published beside the submission for the duration of judging,
on a throwaway cluster holding synthetic data only. If publishing a key to anonymous
verifiers turns out to be outside Cockroach Labs' terms, this tier degrades exactly as
[`FALLBACK.md`](FALLBACK.md) describes, and it says so on the day rather than quietly
dropping the tier.

**Lead with Tier 2, not with this.** Reproducing the merge refusal on your own laptop
needs no credential of ours at all, and it is the stronger claim. See
[`../VERIFY.md`](../VERIFY.md).

---

## The envelope these prompts are shaped around

These are documented limits of the Managed MCP Server, not preferences of ours. The
binding one is the response cap: at the cap the server **truncates rather than
raising**, so a partial answer about how much is currently blocked arrives looking
exactly like a complete one. Every prompt below is aggregate-first because of it.

| Limit | Value |
|---|---|
| Endpoint | `https://cockroachlabs.cloud/mcp` |
| Cluster pin header | `mcp-cluster-id` |
| Statements per call | `1` |
| Characters per statement | `16384` |
| Statement timeout (s) | `20` |
| Response cap (bytes) | `10240` |
| Our budget (bytes) — 80 % of the cap | `8192` |
| SELECT page (rows) | `25` |
| Unreachable schemas | `system`, `crdb_internal`, `pg_catalog`, `information_schema`, `pg_extension` |
| Never issued to any MCP account | `mainline_qa` |
| The entire write surface | `mainline_meas.external_attestation` |

**The `ORDER BY` in these prompts does not reach past the view's own page.** Every mainline_audit view applies its OWN `ORDER BY … LIMIT 25` inside the view. An `ORDER BY` in the statement below therefore RE-ORDERS the page the view already chose; it does not reach past it for a different page. When `rows_complete` is false the rows you are looking at are the view's top 25 by the view's ordering, and the ones you would most like to see may not be among them.

**Why every prompt carries an explicit `LIMIT 25`.** Every statement carries an explicit `LIMIT 25` rather than relying on the server's default page of the same size. A result of exactly 25 rows is therefore the shape a truncated result has, and `judge/runner.py` flags it as `possibly_truncated` independently of anything the view reports about itself.

---

## The questions

### Q01 · What is the database refusing to merge right now, and who has been overriding?

**verb** `select_query` · **view** `mainline_audit.v_open_gate_summary` · **defined in** `verticals/mainline/db/migrations/0156_v_open_gate_summary.sql`

```sql
SELECT site_id, state, permits, open_blocking, open_residue, open_conflicts,
       open_warrants, unmodelled_assets, unmet_floor, countersigned, under_hold,
       overrides_30d, group_count, rows_complete
  FROM mainline_audit.v_open_gate_summary
 ORDER BY open_blocking DESC, site_id
 LIMIT 25;
```

**What a green answer proves.** The five counters summed here are the five plain-column CHECKs that refuse a merge, so this is the state of the gate as the gate itself reads it, aggregated. Nothing in the view computes a judgement; it sums trigger-written scalars.

**What it does not prove.**

- Not a merge prediction. `open_blocking = 0` means the counters read zero at the moment you asked. The gate re-derives inside the merge transaction and pins the epoch, so a precursor arriving a moment later is an ordinary serializable history and this view has no opinion about it.
- Not site-scoped by identity. Which SQL identity the managed endpoint runs as is a day-1 question (GT-10) and the pessimistic answer is assumed, so this view is built to be safe when read in full: counts, states and site ids, no clause text, no narrative, and no person.

**Truncation guard.** `rows_complete`, `group_count`, plus `row_count_equals_limit` — the runner flags a result of exactly 25 rows as possibly truncated whatever the view says about itself.

### Q02 · Which weakenings of controls written over severe ancestry have never been answered for?

**verb** `select_query` · **view** `mainline_audit.v_weakenings_without_disposition` · **defined in** `verticals/mainline/db/migrations/0157_v_weakenings_without_disposition.sql`

```sql
SELECT site_id, activity_root, sev_max, n, n_removed, most_recent,
       ancestry_complete, closures_absent, closures_truncated,
       group_count, rows_complete
  FROM mainline_audit.v_weakenings_without_disposition
 ORDER BY sev_max DESC, n DESC
 LIMIT 25;
```

**What a green answer proves.** This is the accusation surface: MAINLINE's own list of weakenings over severe ancestry for which no disposition exists. `sev_max` is a projected accumulator fed only by active blame edges, and inferred edges are kept out of the active set, so no model output can raise the number that puts a row on this list.

**What it does not prove.**

- Not a list of unsafe clauses. A weakening with no disposition may simply be a weakening no permit has cited yet; the obligation materialises when a subject cites the clause. Reading it as a defect list overstates it.
- `ancestry_complete = false` means the closure was truncated at the ancestor cap or is absent entirely, and the counts beside it are then lower bounds. It fails closed on purpose: absence reports false, not null.

**Truncation guard.** `ancestry_complete`, `closures_absent`, `closures_truncated`, `rows_complete`, plus `row_count_equals_limit` — the runner flags a result of exactly 25 rows as possibly truncated whatever the view says about itself.

### Q03 · How deep does the blame ancestry actually go, and how much of it was walked?

**verb** `select_query` · **view** `mainline_audit.v_blame_coverage` · **defined in** `verticals/mainline/db/migrations/0158_v_blame_coverage.sql`

```sql
SELECT site_id, virulence, clause_versions, truncated_closures, max_depth,
       max_ancestors, max_severity, max_closure_gen, total_generations,
       last_computed_at, ancestry_complete, group_count, rows_complete
  FROM mainline_audit.v_blame_coverage
 ORDER BY virulence DESC, site_id
 LIMIT 25;
```

**What a green answer proves.** `max_depth` is the answer to "is the blame walk one hop deep?" — the question a sceptical reader should ask of any provenance claim, and the one a fluent synthetic corpus fails. `total_generations` rises when a mass rewrite regenerates closures, so a sudden jump is visible rather than silent.

**What it does not prove.**

- Depth is not correctness. A deep closure over a synthetic corpus is deep because the corpus was authored with causal structure; it is not evidence about a real repository. See DEMO-HONESTY.md §2.

**Truncation guard.** `ancestry_complete`, `truncated_closures`, `rows_complete`, plus `row_count_equals_limit` — the runner flags a result of exactly 25 rows as possibly truncated whatever the view says about itself.

### Q04 · Are dispositions keeping up with what was surfaced? Show orphans and the worst ancestor severity per site and quarter.

**verb** `select_query` · **view** `mainline_audit.v_disposition_coverage` · **on camera** beat 5 (`s19-beat5-mcp-connect`) · **transcribed from** `verticals/mainline/demo/VERIFY.md` · **defined in** `verticals/mainline/db/migrations/0159_v_disposition_coverage.sql`

```sql
SELECT site_id, q, surfaced, dispositioned, orphans,
       worst_ancestor, worst_severity, ancestry_complete, rows_complete
  FROM mainline_audit.v_disposition_coverage
 ORDER BY orphans DESC, q DESC
 LIMIT 25;
```

**What a green answer proves.** `orphans` counts obligations that were surfaced and never dispositioned. A system that cannot answer this about itself is not answering it favourably; it is not answering it.

**What it does not prove.**

- Nothing here separates a considered disposition from a rubber stamp, and no column in this view is evidence about anyone's care. What the schema does instead is in DEMO-HONESTY.md §5.
- `dispositioned` counts signatures against obligations, not the quality of the reasoning attached to them.

**Truncation guard.** `ancestry_complete`, `rows_complete`, plus `row_count_equals_limit` — the runner flags a result of exactly 25 rows as possibly truncated whatever the view says about itself.

### Q05 · What did you decline to surface, and with what arithmetic?

**verb** `select_query` · **view** `mainline_audit.v_silence_summary` · **on camera** beat 5 (`s21-beat5-silence`) · **transcribed from** `verticals/mainline/demo/VERIFY.md` · **defined in** `verticals/mainline/db/migrations/0160_v_silence_summary.sql`

```sql
SELECT site_id, source, reason, severity, n,
       mean_score, mean_threshold, nearest_miss
  FROM mainline_audit.v_silence_summary
 ORDER BY severity DESC, n DESC
 LIMIT 25;
```

**What a green answer proves.** `nearest_miss` is the highest score that still fell under threshold — the closest the system came to speaking and did not. A band whose nearest miss sits a thousandth under its threshold is a calibration finding rather than a clean report.

**What it does not prove.**

- Not that the silence was correct. It is a disclosure of the arithmetic, and the arithmetic being disclosed is the claim. Whether the threshold is right is what the recall calibration panel measures, and full calibration is deferred work.

**Truncation guard.** `row_count_equals_limit`.

> Transcribed verbatim from demo/VERIFY.md, which selects the arithmetic columns and not the completeness pair. That file is the authority for what appears on camera and this pack does not edit it. Q05F below is the same question with the view's own completeness columns attached, and the runner's row-count guard applies to both.

### Q05F · The same silence question, with the view's own completeness columns, for a reader who is not restricted to the on-camera prompt.

**verb** `select_query` · **view** `mainline_audit.v_silence_summary` · **defined in** `verticals/mainline/db/migrations/0160_v_silence_summary.sql`

```sql
SELECT site_id, source, reason, severity, n,
       mean_score, mean_threshold, nearest_miss, scoreless, most_recent,
       ancestry_complete, group_count, rows_complete
  FROM mainline_audit.v_silence_summary
 ORDER BY severity DESC, n DESC
 LIMIT 25;
```

**What a green answer proves.** `scoreless` counts silences that carry no score at all — a decline with no arithmetic behind it is a different object from a decline that missed a threshold, and the view refuses to average the two together.

**What it does not prove.**

- `ancestry_complete` here reports whether the group's reason was the ancestor-cap truncation, not whether the retrieval was exhaustive over anything.

**Truncation guard.** `ancestry_complete`, `rows_complete`, plus `row_count_equals_limit` — the runner flags a result of exactly 25 rows as possibly truncated whatever the view says about itself.

### Q06 · Does the recall arithmetic balance — does every candidate end up blocking, advisory, silenced or deduped?

**verb** `select_query` · **view** `mainline_audit.v_recall_conservation` · **defined in** `verticals/mainline/db/migrations/0161_v_recall_conservation.sql`

```sql
SELECT site_id, d, runs, candidates, blocking, advisory, silenced, deduped,
       bonded_sev5, bonded_sev5_blocking, any_degraded, conserved,
       fatalities_all_blocking, retrieval_complete, group_count, rows_complete
  FROM mainline_audit.v_recall_conservation
 ORDER BY d DESC, site_id
 LIMIT 25;
```

**What a green answer proves.** `conserved` re-derives the conservation law in the view rather than trusting the counter that the database already CHECKs: candidates must equal blocking plus advisory plus silenced plus deduped. It reads true unless the CHECK is gone, which makes a false here a structural alarm rather than a data quality note.

**What it does not prove.**

- Conservation is over the retrieval that ran. It is never exhaustiveness over the corpus, and the difference is the whole honesty of the mechanism.
- `retrieval_complete` reports that no arm was degraded during the window. It does not report that an undegraded arm found everything there was to find.

**Truncation guard.** `retrieval_complete`, `any_degraded`, `rows_complete`, plus `row_count_equals_limit` — the runner flags a result of exactly 25 rows as possibly truncated whatever the view says about itself.

### Q07 · Is the custody ledger healthy — admissible checkpoints, and any unwitnessed debt?

**verb** `select_query` · **view** `mainline_audit.v_ledger_health` · **defined in** `verticals/mainline/db/migrations/0162_v_ledger_health.sql`

```sql
SELECT site_code, tree_size, checkpoints, admissible_checkpoints,
       inadmissible_checkpoints, time_bounded_checkpoints,
       object_locked_checkpoints, canonicaliser_versions, last_issued_at,
       open_debt, oldest_open_debt_at, witness_complete,
       group_count, rows_complete
  FROM mainline_audit.v_ledger_health
 ORDER BY site_code
 LIMIT 25;
```

**What a green answer proves.** The ledger's own account of itself: how many checkpoints are admissible, how many are time-bounded, how many sit under an object-storage lock, and how much debt is open. The offline verifier in Tier 1 checks the same chain without this endpoint or us.

**What it does not prove.**

- Not split-view resistance. Until an adverse witness is running, the ledger is tamper-evident to a party holding a checkpoint and nothing stronger is claimed.
- `canonicaliser_versions > 1` is a fact about the ledger, not a defect: it means leaves were canonicalised under more than one version, and the verifier needs the matching one.

**Truncation guard.** `witness_complete`, `rows_complete`, plus `row_count_equals_limit` — the runner flags a result of exactly 25 rows as possibly truncated whatever the view says about itself.

### Q08 · How much of what the documents say is installed has actually been checked in the field?

**verb** `select_query` · **view** `mainline_audit.v_fixity_coverage` · **defined in** `verticals/mainline/db/migrations/0163_v_fixity_coverage.sql`

```sql
SELECT site_id, patrol_class, runs, unfinished_runs, scopeless_runs,
       last_completed, in_scope, checked, not_checked, not_checked_ratio,
       coverage_complete, group_count, rows_complete
  FROM mainline_audit.v_fixity_coverage
 ORDER BY not_checked_ratio DESC NULLS LAST, site_id
 LIMIT 25;
```

**What a green answer proves.** `not_checked_ratio` is the gap between as-documented and as-operated, per patrol class. A high ratio is the honest reading of "we do not know", which is a different answer from "it is fine".

**What it does not prove.**

- Not live plant state. There is no live OT connectivity anywhere in this system and nothing is auto-remediated; ingestion is a periodic one-way export from the OT DMZ.
- `coverage_complete` fails closed: an unfinished run, an unchecked asset or an empty declared scope all report false.

**Truncation guard.** `coverage_complete`, `unfinished_runs`, `rows_complete`, plus `row_count_equals_limit` — the runner flags a result of exactly 25 rows as possibly truncated whatever the view says about itself.

### Q09 · What have the agents been doing, and did any of them fail in a way nobody modelled?

**verb** `select_query` · **view** `mainline_audit.v_agent_actions` · **defined in** `verticals/mainline/db/migrations/0164_v_agent_actions.sql`

```sql
SELECT agent_role, tool, outcome, n, last_at, transports, retryable,
       modelled_refusals, unmodelled_refusals, model_ids, prompt_versions,
       mean_latency_ms, outcomes_modelled, group_count, rows_complete
  FROM mainline_audit.v_agent_actions
 ORDER BY n DESC, agent_role
 LIMIT 25;
```

**What a green answer proves.** Every agent action is attributed to a role, a tool, a model id and a prompt version. `unmodelled_refusals > 0` means a SQLSTATE arrived that the error taxonomy does not model — a refusal nobody designed — and the flag fails closed on it.

**What it does not prove.**

- An agent's report is evidence that a review occurred, never evidence of a condition. That is why each finding elsewhere carries the SQL it ran and the digest of its result rows: so it can be re-run rather than believed.

**Truncation guard.** `outcomes_modelled`, `unmodelled_refusals`, `rows_complete`, plus `row_count_equals_limit` — the runner flags a result of exactly 25 rows as possibly truncated whatever the view says about itself.

### Q10 · Prove the vector search actually used an index. Show me the plan.

**verb** `explain_query` · **on camera** beat 5 (`s20-beat5-explain`) · **transcribed from** `verticals/mainline/demo/VERIFY.md` · **defined in** `verticals/mainline/db/migrations/0041_event_cue_embedding.sql`

```sql
EXPLAIN
SELECT c.cue_id
  FROM mainline.event_cue_embedding@cue_scoped_idx AS c
 WHERE c.site_id = $1 AND c.scope_id = $2 AND c.facet = $3
 ORDER BY c.emb <=> $4
 LIMIT 10;
```

**What a green answer proves.** A `vector search` node on `cue_scoped_idx` with a non-empty `prefix spans:` line is the index being traversed, printed by the server, over an endpoint we do not operate.

**What it does not prove.**

- Not that the retrieval was exhaustive, and not that an approximate-nearest-neighbour result is replayable bit for bit. What is claimed is replayability of the arithmetic and of the disclosed boundary.
- Whether `explain_query` renders this fragment over the managed endpoint at all is day-1 check GT-07. If it does not, the assertion runs over pgwire and the claim is stated at that strength instead of this one.

**Read the plan for** a `vector search` node on `mainline.event_cue_embedding@cue_scoped_idx` with a non-empty `prefix spans:` line.

The substrings the film requires, read from `demo/REFUSAL-STRINGS.yaml`: `vector search`, `prefix spans`.

**Before you send it.** `$1` to `$4` are placeholders. The Managed-MCP verbs take a statement, not a parameter list, so a judge substitutes literals before sending. `judge/cli.py envelope` binds them for you and prints the resulting length against the 16 384-character cap, and `judge/cli.py run --via sql` sends the bound form.

- $1 — a site_id UUID literal, e.g. '00000000-0000-4000-8000-000000000001'::UUID
- $2 — a scope_id UUID literal from the same site
- $3 — a facet, which must be one of the five `event_cue.facet` CHECK allows: 'mechanism', 'precondition', 'control_failure', 'recurrence_test', 'narrative'. A value outside that set is not merely empty, it is a value the column cannot hold.
- $4 — a 1024-dimension vector literal, e.g. '[0.01,-0.02, …]'::VECTOR(1024)

**Measured, not assumed.** Bound to a worst-case 1024-dimension literal at six significant figures this statement is **10526 characters** against a 16384 cap — fits, with 5858 characters of headroom. The width is read from `verticals/mainline/db/migrations/0041_event_cue_embedding.sql` at render time, so widening the embedding column turns this page red instead of turning the take red.

**Truncation guard.** `plan_substrings`.

> The index is named explicitly because at demo corpus scale the optimizer does not choose it: the plan becomes top-k, render, filter, scan. That is a measurement recorded in ADR 0002 F1, and pinning the index is the more deterministic engineering anyway — a plan that flips on table statistics has no business sitting beneath a safety gate.

> Every prefix column is constrained to a single value. A prefix constrained with `IN (...)` does not qualify, which is why an ancestry walk is one such statement per ancestor, unioned and re-ranked, rather than one statement with a list.

> MEASURED, not assumed: this statement was bound to type-valid literals and run on a local CockroachDB CCL v26.2.5 node on 2026-08-10. The index hint written before the alias parses, the 10 526-character bound statement is accepted, and the plan carries `vector search` on `cue_scoped_idx` with a NON-EMPTY `prefix spans:` line naming all three prefix values. The plan is `top-k -> render -> lookup join -> vector search`, so the index is traversed and the primary key is joined back for the projection.

> What that measurement does NOT settle is whether `explain_query` renders the same fragment over the Managed MCP endpoint. That is day-1 check GT-07 and it is settled by `tests/integration/mcp/test_explain_index_truth.py` against the live endpoint, not by this pack. Until then the claim is stated at pgwire strength.

### Q10C · The same plan proof against the 256-dimension coarse sidecar, whose vector literal is a quarter the size.

**verb** `explain_query` · **defined in** `verticals/mainline/db/migrations/0042_event_cue_coarse.sql`

```sql
EXPLAIN
SELECT c.cue_id
  FROM mainline.event_cue_coarse@cue_sweep_idx AS c
 WHERE c.tenant_id = $1
 ORDER BY c.emb_coarse <=> $2
 LIMIT 10;
```

**What a green answer proves.** The same two properties as Q10 — a named index and a single-valued prefix — on the sweep index that runs as insurance against taxonomy-induction error.

**What it does not prove.**

- The coarse sweep is insurance, not the primary channel. A plan proof here says nothing about whether the scoped arms in Q10 ran.

**Read the plan for** a `vector search` node on `mainline.event_cue_coarse@cue_sweep_idx` with a non-empty `prefix spans:` line.

The substrings the film requires, read from `demo/REFUSAL-STRINGS.yaml`: `vector search`, `prefix spans`.

**Before you send it.** One prefix column and a 256-dimension literal, so the bound statement is roughly a quarter of Q10's length. Use this when the full-width literal crowds the character cap or when a shorter paste is easier to read on a call. Measured on the same local v26.2.5 node on 2026-08-10: 2 756 characters bound, plan `vector search` on `cue_sweep_idx` with a non-empty `prefix spans:` line.

- $1 — the deployment's tenant_id UUID literal
- $2 — a 256-dimension vector literal, renormalised client-side

**Measured, not assumed.** Bound to a worst-case 256-dimension literal at six significant figures this statement is **2756 characters** against a 16384 cap — fits, with 13628 characters of headroom. The width is read from `verticals/mainline/db/migrations/0042_event_cue_coarse.sql` at render time, so widening the embedding column turns this page red instead of turning the take red.

**Truncation guard.** `plan_substrings`.

---

## Now try to break it — the negatives matter more than the positives

Every statement in this section **must fail**. A negative suite that has quietly gone
green is the worst artefact in a repository, because it reads as the strongest. Our own
client refuses each of these before transmission and names the limit it broke; the
server-side half is asserted by `tests/integration/mcp/test_negative_reachability.py`,
which deliberately bypasses that screen — a control that lives only in our client is a
control an attacker skips by not using our client.

**Run these over MCP only.** On a pgwire connection as cluster admin they succeed, and
reporting that as a pass would invert their meaning.

### N01 · Can an MCP identity read the per-person deliberation measurements?

```sql
SELECT count(*) FROM mainline_qa.v_disposition_profile;
```

**Must fail because.** mainline_qa holds per-person deliberation measurement, which runs only behind a customer-signed notified policy and writes a record every time it is read. No MCP service account is issued for that schema on any tier, ever.

**What the failure proves.** When this fails, the exclusion is a property of the deployment rather than a promise in a document.

**What it does not prove.**

- A refusal here says nothing about whether the schema exists or what is in it, and that is the intended amount of information to leak.

### N02 · Can an MCP identity reach the cluster's internal job catalogue?

```sql
SELECT count(*) FROM crdb_internal.jobs;
```

**Must fail because.** The Managed MCP tools cannot reach `crdb_internal` at all. That is a property of the server, not of our client.

**What the failure proves.** That `crdb_internal` is unreachable is what makes the mainline_audit ops views the API rather than a bypass around one: with no system catalogue, an operator question has nowhere to go except a view we wrote, versioned and budgeted.

**What it does not prove.**

- Unreachability over MCP is not unreachability over pgwire. A cluster admin on a SQL connection reads `crdb_internal` freely, and the bypass beat exists to show what an administrator can in fact do.

### N03 · Can an MCP identity read the PostgreSQL compatibility catalogue?

```sql
SELECT count(*) FROM pg_catalog.pg_class;
```

**Must fail because.** `pg_catalog` is one of the five schemas the Managed MCP tools cannot reach.

**What the failure proves.** The same structural point as N02, on a second catalogue.

**What it does not prove.**

- Nothing beyond reachability. It is a probe, not a security proof.

### N04 · Can an MCP identity enumerate the schema through information_schema?

```sql
SELECT count(*) FROM information_schema.tables;
```

**Must fail because.** `information_schema` is one of the five unreachable schemas.

**What the failure proves.** Schema enumeration goes through `list_tables` and `get_table_schema`, which are themselves paged and capped, rather than through an unbounded catalogue scan.

**What it does not prove.**

- Nothing beyond reachability.

---

## Asserted elsewhere, because it cannot be pasted

**A01 — `insert_rows` cannot write anywhere except `mainline_meas.external_attestation`.**

Bound into the SIGNATURE of the write verb in `packages/mainline-mcp`, not checked at run time: the supported client API has no parameter that names a table, so "insert into something else" is not a call a caller can express. The server-side half is in `tests/integration/mcp/test_negative_reachability.py`.

*Why it is not a question here:* It is the absence of a parameter, and an absence cannot be pasted.

**A02 — The audit views fit the response budget with headroom as the corpus grows.**

`packages/mainline-mcp` measures actual response bytes per view and fails at 8 KiB rather than at the server's 10 KiB, so the alarm fires with a fifth of the budget still unused.

*Why it is not a question here:* It is a nightly measurement over time, not a single answer.

---

## What this page is checked against

| Authority | What it settles |
|---|---|
| `verticals/mainline/db/migrations/*_v_*.sql` | every column a prompt selects exists in the shipped view |
| `verticals/mainline/db/migrations/0041, 0042` | the vector width, so the bound `EXPLAIN` is measured against the character cap |
| `verticals/mainline/demo/VERIFY.md` | every judge-facing statement is a question here or a stated exemption |
| `verticals/mainline/demo/REFUSAL-STRINGS.yaml` | the index name, the prefix columns and the plan substrings |
| `scripts/demo/claim_hygiene.py` | this page's own prose, under the same rules as the rest of the published surface |

```bash
python verticals/mainline/demo/judge/cli.py validate   # envelope, negatives, drift
python verticals/mainline/demo/judge/cli.py render --check
python verticals/mainline/demo/judge/cli.py run --via sql    # needs TRAPPOINT_DSN
python verticals/mainline/demo/judge/cli.py run --via mcp    # needs a published key
```

Both `run` modes **exit non-zero when they had nothing to talk to**. A green run with no
cluster behind it would assert nothing, and a green *negative* run with no cluster behind
it would assert the opposite of what it claims.

Authorities this pack implements rather than re-derives:

- ARCHITECTURE.md §9.1 (the Managed-MCP surface, its verbs and its limits)
- ARCHITECTURE.md §17 (the mainline_audit view family, and mainline_qa's exclusion)
- ARCHITECTURE.md §19 GT-07 (does explain_query render the vector fragment), GT-10, GT-17
- docs/adr/0002-g1-platform-ground-truth.md F1 (the index is traversed only when named)
- verticals/mainline/demo/VERIFY.md (Tier 3 — the three prompts used on camera)
- verticals/mainline/demo/REFUSAL-STRINGS.yaml (`explain_fragment`)
