<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The recall audit views — column contract

**Normative for `mainline_audit.v_recall_conservation` and `mainline_audit.v_silence_summary`.**

The recall domain owns the tables (`mainline_meas.recall_run`, `recall_candidate`,
`silence_receipt`, `silence_ledger`, `recall_certificate`; migrations `0080–0087`). **The MCP
lead owns the views.** This document is the requirement they are written against, so that a
column added or renamed under a view is a change to a published contract rather than a
surprise in someone else's demo.

Both views are read through the Managed MCP surface, which is read-only by default and caps a
`SELECT` at **25 rows** with a **10 KiB** response and a **20 s** timeout. Every shape below is
designed to survive that envelope: aggregate first, one row per subject, no wide JSONB.

---

## 0. Two things that are true of both views

**Neither view may expose suppressed cue text, narrative, or any candidate's content.** The
silence ledger's evidentiary value comes from being a contemporaneous business record of a
*decision*, with its arithmetic. It is not a reading room for the material that was withheld.
The columns below carry identifiers, scores, thresholds and counts, and nothing that would let
a reader reconstruct what a suppressed precursor said.

**Neither view may hide a truncation.** Every aggregate that could be short carries the fact
alongside it: `arms_degraded`, `not_exhaustive`, `certificate_verdict`. A truncated result that
is indistinguishable from a complete one is the exact defect CUE HORIZON exists to refuse, and
a view is as capable of committing it as a retrieval is.

---

## 1. `mainline_audit.v_recall_conservation`

One row per `recall_run`. The question it answers is *"did the arithmetic hold, and does the
receipt commit to what the run says it found?"*

| Column | Type | Source | Contract |
|---|---|---|---|
| `run_id` | `UUID` | `recall_run.run_id` | Primary key of the view. |
| `permit_id` | `UUID` | `recall_run.permit_id` | The gated subject. |
| `site_id` | `UUID` | `recall_run.site_id` | RLS scope. |
| `started_at` | `TIMESTAMPTZ` | `recall_run.started_at` | Sort key; `DESC` is the default order. |
| `latency_ms` | `INT4` | `recall_run.latency_ms` | Nullable: a run that never reported is not a run that took zero. |
| `policy_version` | `STRING` | `recall_run.policy_version` | The anchored policy the run cited (MI18). |
| `n_candidates` | `INT4` | `recall_run.n_candidates` | |
| `n_blocking` | `INT4` | `recall_run.n_blocking` | |
| `n_advisory` | `INT4` | `recall_run.n_advisory` | |
| `n_silenced` | `INT4` | `recall_run.n_silenced` | |
| `n_deduped` | `INT4` | `recall_run.n_deduped` | |
| `n_partition` | `INT4` | derived | `n_blocking + n_advisory + n_silenced + n_deduped`. |
| `conserved` | `BOOL` | derived | `n_candidates = n_partition`. **Must always be `true`;** `candidates_conserved` (MI17) refuses the row otherwise. A `false` here means the CHECK was dropped, and that is the finding. |
| `n_rows_observed` | `INT4` | `count(*)` over `recall_candidate` | The independent count. |
| `rows_match_counters` | `BOOL` | derived | `n_rows_observed = n_candidates`. Detects counter drift between the run row and the rows it claims to summarise — the same defence-in-depth re-derivation the merge gate performs. |
| `n_bonded_sev5` | `INT4` | `recall_run.n_bonded_sev5` | Trigger-maintained (`fn_bonded_sev5`, 0113). Never an input. |
| `n_bonded_sev5_blocking` | `INT4` | `recall_run.n_bonded_sev5_blocking` | |
| `fatalities_all_blocking` | `BOOL` | derived | `n_bonded_sev5_blocking = n_bonded_sev5` (MI16). |
| `arms_degraded` | `BOOL` | `recall_run.arms_degraded` | The run completed on channels A+B only. |
| `index_generation` | `STRING` | `recall_run.index_generation` | |
| `index_plan_digest_hex` | `STRING` | `encode(recall_run.index_plan_digest,'hex')` | Hex, not `BYTES`: the MCP response is text and a raw byte column wastes the 10 KiB budget on escapes. |
| `certificate_verdict` | `STRING` | `recall_certificate.verdict` | `complete` / `partial` / `UNDETERMINED`. `NULL` only if no certificate was written, which is itself a finding. |
| `coverage_basis` | `STRING` | `recall_certificate.coverage_basis` | |
| `silence_receipt_id` | `UUID` | `silence_receipt.silence_receipt_id` | |
| `candidate_root_hex` | `STRING` | `encode(silence_receipt.candidate_root,'hex')` | The PER commitment. |
| `theta` | `FLOAT8` | `silence_receipt.theta` | The lowest score actually shown to a human. |
| `s` | `INT4` | `silence_receipt.s` | |
| `n` | `INT4` | `silence_receipt.n` | |
| `receipt_covers_run` | `BOOL` | derived | `silence_receipt.n = recall_run.n_candidates`. A receipt committing to a different population than the run recorded is the shape of a hand-edit. |

**Join discipline.** `recall_certificate` is `UNIQUE (run_id, index_generation)`, so join on
`(run_id, index_generation)` — joining on `run_id` alone can multiply rows the day a run is
re-certified under a new generation. `silence_receipt` is one row per run in normal operation
but is not constrained to be; take the latest by `issued_at` and expose that choice in the
view definition rather than in a comment.

---

## 2. `mainline_audit.v_silence_summary`

One row per `(site_id, subject_kind, subject_id)`. The question it answers is the plaintiff's:
*"your system knew about event X and did not show it — how often, on what basis, and against
what threshold?"*

| Column | Type | Source | Contract |
|---|---|---|---|
| `site_id` | `UUID` | `silence_ledger.site_id` | |
| `subject_kind` | `STRING` | `silence_ledger.subject_kind` | |
| `subject_id` | `UUID` | `silence_ledger.subject_id` | Grouping key with the two above. |
| `severity` | `INT2` | `max(silence_ledger.severity)` | The worst thing that was silenced about this subject. |
| `n_silences` | `INT8` | `count(*)` | |
| `first_at` | `TIMESTAMPTZ` | `min(at)` | |
| `last_at` | `TIMESTAMPTZ` | `max(at)` | |
| `n_below_tau` | `INT8` | `count(*) FILTER (WHERE reason='below_tau')` | |
| `n_model_refusal` | `INT8` | filtered count | The corpus is cyanide leaching, H₂S and confined-space chemistry; a refusal on a clean document is plausible and must be counted separately, never folded into "below threshold". |
| `n_dedup_sibling` | `INT8` | filtered count | |
| `n_cap_exceeded` | `INT8` | filtered count | |
| `n_truncated` | `INT8` | filtered count | |
| `n_abstained` | `INT8` | filtered count | |
| `n_bounded_negative` | `INT8` | filtered count | |
| `n_unreachable` | `INT8` | filtered count | |
| `max_score` | `FLOAT8` | `max(score)` | The closest call. Nullable: not every reason carries a score. |
| `min_threshold` | `FLOAT8` | `min(threshold)` | The most permissive bar this subject was measured against. |
| `closest_margin` | `FLOAT8` | `min(threshold - score) FILTER (WHERE reason='below_tau')` | **The number a supervisor and a court both want.** A margin of 0.01 on a severity-4 precursor is a different conversation from a margin of 0.6, and an aggregate that only reported counts would flatten them. |
| `n_sources` | `INT8` | `count(DISTINCT source)` | Recall is one of ten sources in the `source` vocabulary; a subject silenced by several is a different pattern from one silenced repeatedly by one. |
| `policy_versions` | `STRING[]` | `array_agg(DISTINCT policy_version)` | Bounded in practice by the number of anchored policies; if this ever needs a cap, cap it and add `policy_versions_truncated BOOL`. |
| `severity_5_silenced` | `BOOL` | derived | `bool_or(severity = 5)`. **A `true` here is an incident, not a statistic** — a bonded severity-5 event cannot be silenced by the recall path (MI16), so a `true` means either a non-recall source or a defect, and the reader must be able to see it without a `WHERE`. |

**Ordering and the row cap.** Default `ORDER BY severity DESC, closest_margin ASC NULLS LAST,
last_at DESC`. Under a 25-row cap the first page must be the most serious near-misses, not the
most recent noise — an audit surface whose default page is chronological is an audit surface
that hides the interesting row on page 40.

---

## 3. What these views must never become

They must not gain a `WHERE severity >= n` or any other default filter. The value of the
silence ledger is that it is *complete*; a view that quietly narrowed it would reintroduce, at
the read side, precisely the selective disclosure the ledger exists to make impossible.

They must not join to `event.narrative`, `event_cue.cue_text`, or any content column. If a
reader needs the content of a silenced precursor, that is a disclosure decision with an actor
and a `disclosure_event` row, not a column in an aggregate.
