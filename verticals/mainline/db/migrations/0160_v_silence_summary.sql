-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0160_v_silence_summary.sql
-- CREATE VIEW mainline_audit.v_silence_summary — every warning we chose not to give
--
-- MI: MI17, MI16
-- I: I13
-- COUNSEL-GATED: yes
-- RATIONALE: The plaintiff's actual question is "your system knew about event X and did not
--            show it". Without the silence ledger the answer is silence plus an adverse
--            inference; with it the answer is arithmetic. This view is the aggregate face of
--            that ledger, and `nearest_miss` is the column that earns it: the highest score
--            that still fell under threshold is the closest the system came to speaking, and
--            a band where the nearest miss sits at 0.449 against a 0.45 threshold is a
--            calibration finding rather than a clean report.
--
-- migration:  0160_v_silence_summary
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI17 — recall candidates are exactly partitioned
--                    (candidates = blocking + advisory + silenced + deduped). This view
--                    reports the `silenced` term; `v_recall_conservation` reports the sum.
--             MI16 — every severity-5 event bonded to the permit's activity node or an
--                    ancestor is blocking. `severity` here is projected from
--                    `event.severity_gate`, so a severity-5 row appearing in this ledger
--                    under source 'recall' would be a live contradiction with
--                    `bonded_fatalities_all_blocking`, and that is why severity is grouped on.
--             I13  — silence is logged, with its arithmetic, in the same transaction as the
--                    decision.
-- source:     ARCHITECTURE.md §17 (view definition) · §5.7 (silence_ledger DDL and the three
--             controls on it) · §9.1 · correction S10
-- requires:   0084 mainline_meas.silence_ledger
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
-- The gate is over WHO MAY READ this, never over whether it is written. SEC-0: MAINLINE never
-- chooses not to record a fact; it chooses only where the fact lives and who may read it. A
-- system that deliberately declines to record whether it stayed silent is a WORSE exhibit than
-- one that records the silence, because the decision to blind ourselves is itself
-- discoverable, dated and authored. The ledger stays in the unprivileged measurement zone
-- (`mainline_meas`) precisely so that its evidentiary value comes from being a contemporaneous
-- business record made in the ordinary course of business.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY `nearest_miss` IS max(score) AND WHY THAT IS NOT A TYPO
-- ─────────────────────────────────────────────────────────────────────────────
-- Every row in this ledger is something the system declined to surface, so every
-- score in it is BELOW its threshold. The maximum of those scores is therefore
-- the nearest the system came to speaking and not speaking — the top of the
-- suppressed set, not the bottom. `mean_score` says how far under the band sits
-- on average; `nearest_miss` says how close the closest call was. A calibration
-- argument needs both, and a cross-examination will only ask for the second.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THE ROUNDING IS EXPLICIT AND WHY 3 PLACES
-- ─────────────────────────────────────────────────────────────────────────────
-- FLOAT8 rendered at full precision costs ~20 bytes per number, and this view
-- carries four of them across up to 25 rows against a 10 KiB response cap.
-- Rounding to 3 places is the difference between a response that fits and a
-- response the transport truncates — and a truncated audit response is the
-- failure mode this whole band is shaped to prevent. Three places is also the
-- precision the thresholds themselves are calibrated to, so nothing is lost that
-- was ever meaningful.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. IT IS NOT PROOF OF EXHAUSTED RECALL. PER proves exhaustion of the retrieval
--    that ran, not of the corpus (§5.7), and it lives on `silence_receipt` with
--    its Merkle boundary proof. This view is a rollup of DECISIONS, not a proof
--    about a candidate set.
-- 2. IT NAMES NO PERSON. `subject_id` is a permit or change-request id.
--    Threshold arithmetic about a retrieval is not a characterisation of a human
--    (I15), and keeping it that way is what lets this ledger sit on the MCP
--    surface at all.

CREATE VIEW mainline_audit.v_silence_summary AS
  WITH g AS (
    SELECT s.site_id                             AS site_id,
           s.source                              AS source,
           s.reason                              AS reason,
           s.severity                            AS severity,
           count(*)                              AS n,
           round(avg(s.score)::NUMERIC, 3)       AS mean_score,
           round(avg(s.threshold)::NUMERIC, 3)   AS mean_threshold,
           round(max(s.score)::NUMERIC, 3)       AS nearest_miss,
           count(*) FILTER (WHERE s.score IS NULL) AS scoreless,
           max(s.at)                             AS most_recent
      FROM mainline_meas.silence_ledger s
     WHERE s.at > now() - INTERVAL '90 days'
     GROUP BY s.site_id, s.source, s.reason, s.severity
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.site_id        AS site_id,
         g.source         AS source,
         g.reason         AS reason,
         g.severity       AS severity,
         g.n              AS n,
         g.mean_score     AS mean_score,
         g.mean_threshold AS mean_threshold,
         g.nearest_miss   AS nearest_miss,
         g.scoreless      AS scoreless,
         g.most_recent    AS most_recent,
         -- The truncation flag, in the form this table can honestly support. `reason =
         -- 'truncated'` is a closure that hit the 512-ancestor cap and spilled; any group
         -- carrying that reason is a group whose ancestry was NOT walked to the end.
         (g.reason <> 'truncated') AS ancestry_complete,
         t.group_count    AS group_count,
         (t.group_count <= 25) AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.severity DESC, g.n DESC, g.site_id
   LIMIT 25;
