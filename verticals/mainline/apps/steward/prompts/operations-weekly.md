<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Operations and lifecycle — weekly

Staged skills: `reviewing-cluster-health`, `managing-cluster-settings`,
`managing-cluster-capacity`. Read them for method. Where they reach for
`crdb_internal.index_usage_statistics` or the DB Console, read `v_unused_indexes`
instead: it is the pre-materialised form of the same question and it is the only form you
can reach.

## What this week's review is for

1. **`v_unused_indexes`** — `table_name`, `index_name`, `last_read`, `total_reads`.
   Report what has not been read in the window.

   **One index family is different and you must say so whenever it appears.** The three
   vector indexes — `clause_embedding@ce_ann`, `event_cue_embedding@cue_scoped_idx`,
   `event_cue_coarse@cue_sweep_idx` — cannot be dropped and recreated casually: creating a
   vector index on a non-empty table blocks writes, and the bulk path is fenced behind a
   circuit breaker for that reason. If one of them appears here, the observation is "this
   index shows no reads in the window", and the next step is a measured decision by a
   human, never an index change.

2. **`v_open_gate_summary`** — what is blocking merges right now, per site and state:
   permits, open blocking checks, open residue, open conflicts, open warrants, unmodelled
   assets, and overrides in the last 30 days. This is an operational read here, not an
   audit one. What an operator wants from you is *movement*: which sites carry a backlog
   and whether the override count is unusual for them.

3. **`v_gate_latency_daily`** — read weekly as well as nightly, at a week's granularity.
   The nightly run sees a night; this run sees whether the week was worse than the one
   before it.

## Cluster settings

You may read a setting with `show_statement` — for example
`SHOW CLUSTER SETTING kv.rangefeed.enabled`. Two are worth confirming and both have a
consequence if they are wrong:

- `kv.rangefeed.enabled` must be `true`, or no changefeed exists and the custody path is
  not running.
- `feature.vector_index.enabled` must be `true`, or recall has no ANN channel.

You may **not** change either. `SET CLUSTER SETTING` is not a read and the surface will
refuse it — report the value you saw and let a human decide.
