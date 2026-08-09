-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0170_v_disposition_profile.sql
-- CREATE VIEW mainline_qa.v_disposition_profile — per-named-person, and therefore NOT on the
-- MCP surface, on any tier, ever (S14)
--
-- MI: MI27, MI29
-- I: I15
-- COUNSEL-GATED: yes
-- RATIONALE: This view is the one object in MAINLINE that produces a derived characterisation
--            of a named human, and everything about where it lives is the control. It is in
--            `mainline_qa`, reachable only by `quality_assurance` and never by any Managed-MCP
--            service account on any tier; every SELECT against it must write a `profile_read`
--            ledger entry naming the actor, the purpose, the filter predicate and the result
--            digest. Observing the observer. If this profile is produced in discovery it
--            arrives with a signed record of who looked, when and why — which is the
--            difference between surveillance and a quality-assurance programme that a court
--            can see.
--
-- migration:  0170_v_disposition_profile
-- domain:     datamodel / dm-views-rls
-- band:       0170-0179z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). ARCHITECTURE
--             §18 wrote this band as 0155-0158 and docs/leads/datamodel.md §3 wrote it as
--             0200-0279; both are revoked by MR-7 and the allocation file is the authority.
-- statements: 1
-- invariants: MI27 — a disposition's identity, rank, org and competency are projections of
--                    `person`, and a missing person row refuses. Every name grouped on here
--                    was written by `fn_disposition_project`, never supplied by a client.
--             MI29 — emergency overrides escalate against the PERSON across subjects, with no
--                    ceiling. `prior_override_max` is the ladder as this person climbed it.
--             I15  — THE ALLEGATION FIREWALL. No SUBSTRATE table may store a threshold, score
--                    or flag characterising a named human's conduct. This is not a substrate
--                    table: it is a vertical view in a schema the substrate does not define,
--                    behind a role the MCP never receives, and the firewall is the schema
--                    boundary itself.
-- source:     ARCHITECTURE.md §17 ("the views that are NOT here (S14)") · §11.5 (SEC-3, the
--             A-RULE, and the vocabulary hygiene list) · §5.5 (disposition DDL) ·
--             correction S14 · docs/leads/datamodel.md DM-16
-- requires:   0066 mainline.disposition
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
--
-- ═════════════════════════════════════════════════════════════════════════════
-- EVERY `SELECT` AGAINST THIS SCHEMA MUST WRITE A `profile_read` LEDGER ENTRY
-- ═════════════════════════════════════════════════════════════════════════════
-- §11.5 is binding: per-signer detail exists only in `mainline_qa`, and every
-- SELECT writes a ledger entry — `entry_kind = 'profile_read'`, carrying actor,
-- purpose, filter predicate and result digest.
--
-- A VIEW CANNOT ENFORCE THAT, and this file will not pretend otherwise. There is
-- no SELECT trigger in PostgreSQL or CockroachDB; a view is a stored query and a
-- stored query writes nothing. The enforcement is three things, none of which is
-- this file:
--
--   1. GRANT SHAPE. `quality_assurance` holds SELECT on `mainline_qa` and, per
--      GRANTS.yaml `denials`, 42501 on every object outside it. It has no other
--      reach, so the only path to this data is the QA service.
--   2. THE QA SERVICE. It opens one SERIALIZABLE transaction, INSERTs the
--      `ledger_intake` row and runs the SELECT in the same transaction, so an
--      unledgered read is not a read that happened quietly — it is a read that
--      rolled back.
--   3. THE LEDGER. That intake row reaches a signed, cosigned checkpoint, so the
--      record of who looked is as tamper-evident as the record they looked at.
--
-- Recording the gap here rather than implying a mechanism is the honest form.
-- P2 is about columns a GATE reads; this is a column a LAWYER reads, and the
-- control for it is procedural, ledgered and stated.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- VOCABULARY HYGIENE IS ENFORCED BY A CI GREP, AND THIS FILE IS ITS FRONT LINE
-- ═════════════════════════════════════════════════════════════════════════════
-- §11.5, applied to every column name below:
--   * `mechanism_absent`, never `not_applicable`. A dismissal is disregard, and
--     disregard is the s.31 element; a falsifiable factual assertion that proves
--     wrong is negligence at worst.
--   * `reading_floor_met`, POSITIVE POLARITY, never `haste_flag`. The consequence
--     is named after the system's obligation (`countersignature_required`), never
--     after the human's character.
--   * `suspected_rubber_stamp` DOES NOT EXIST, in schema or telemetry, ever. It
--     is not below and it is not derivable from what is below, and §11.7 forbids
--     claiming a disposition can be distinguished from a rubber stamp at all.
--   * `signer_sub`, never `approver_id`, and never a metric label — which is why
--     this column appears in a `mainline_qa` view and in no dashboard dimension.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- WHY THE MEDIAN IS COMPUTED BY ROW NUMBERING AND NOT BY percentile_cont
-- ═════════════════════════════════════════════════════════════════════════════
-- A median is the right statistic here — deliberation seconds are heavily
-- right-skewed by interruptions, and a mean is moved by one person taking a
-- phone call. The ordered-set aggregate form
-- (`percentile_cont(0.5) WITHIN GROUP (ORDER BY …)`) is not on the measured
-- capability list for this cluster in docs/leads/datamodel.md, and this file
-- takes no unverified dependency: an unverified function inside a migration is a
-- migration that fails on a fresh cluster and nowhere else.
--
-- The exact median is therefore taken by selecting the middle one or two rows of
-- each partition and averaging them. The predicate is pure integer arithmetic —
-- `rn * 2 BETWEEN n AND n + 2` — with no division, no `div()`, and no cast:
--
--     n = 5 → rn = 3 alone         (5 ≤ 6 ≤ 7)
--     n = 4 → rn = 2 and rn = 3    (4 ≤ 4 ≤ 6 and 4 ≤ 6 ≤ 6)
--
-- `row_number()` and `count(*)` as window functions are ordinary SQL and are
-- used elsewhere in this schema.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- WHAT THIS VIEW IS NOT
-- ═════════════════════════════════════════════════════════════════════════════
-- 1. IT IS NOT A PERFORMANCE MEASURE, AND IT MAY NOT BECOME ONE WITHOUT A ROW
--    IN `person_measure_policy`. SEC-3 makes "counsel-gated" a row the database
--    requires: a person-measure computed over data predating a signed, notified
--    customer policy is not an insertable row. This view computes nothing it
--    persists, so it creates no such row — and the moment its output is used to
--    decide anything about the person, the policy row is a precondition.
-- 2. IT IS NOT EVIDENCE OF INATTENTION. A short deliberation on a routine
--    disposition is a competent person recognising a familiar control.
-- 3. IT IS NOT REACHABLE FROM `mainline_auditor`. That is asserted, not assumed:
--    tests/integration/schema/test_mi_rls.py walks every object in this schema
--    and requires 42501 from the MCP identity on each one.

CREATE VIEW mainline_qa.v_disposition_profile AS
  WITH ranked AS (
    SELECT d.signer_sub           AS signer_sub,
           d.site_id              AS site_id,
           d.deliberation_seconds AS deliberation_seconds,
           row_number() OVER (PARTITION BY d.signer_sub, d.site_id
                                  ORDER BY d.deliberation_seconds) AS rn,
           count(*)     OVER (PARTITION BY d.signer_sub, d.site_id) AS n
      FROM mainline.disposition d
     WHERE d.retracted_by IS NULL
  ),
  medians AS (
    SELECT ranked.signer_sub AS signer_sub,
           ranked.site_id    AS site_id,
           round(avg(ranked.deliberation_seconds)::NUMERIC, 1)
                             AS median_deliberation_seconds
      FROM ranked
     WHERE ranked.rn * 2 >= ranked.n
       AND ranked.rn * 2 <= ranked.n + 2
     GROUP BY ranked.signer_sub, ranked.site_id
  ),
  base AS (
    SELECT d.signer_sub AS signer_sub,
           d.site_id    AS site_id,
           count(*)     AS dispositions,
           count(*) FILTER (WHERE d.kind = 'mechanism_absent')    AS mechanism_absent_n,
           count(*) FILTER (WHERE d.kind = 'emergency_override')  AS emergency_override_n,
           count(*) FILTER (WHERE d.kind = 'accept_residual')     AS accept_residual_n,
           -- Positive polarity throughout (§11.5 / D1). The column counts the times the
           -- floor was NOT met because that is the number the obligation attaches to, and
           -- the obligation is named after the system's response, not the person's haste.
           count(*) FILTER (WHERE NOT d.reading_floor_met)        AS floor_unmet_n,
           count(*) FILTER (WHERE d.countersigner_credential_id IS NOT NULL)
                                                                  AS countersigned_n,
           count(*) FILTER (WHERE d.evidence_opened)              AS evidence_opened_n,
           count(*) FILTER (WHERE d.stale_replay)                 AS stale_replay_n,
           count(*) FILTER (WHERE d.virulence IN ('blood_major', 'blood_fatal'))
                                                                  AS blood_ancestry_n,
           round(avg(d.particularity)::NUMERIC, 4)                AS mean_particularity,
           count(*) FILTER (WHERE d.particularity IS NULL)        AS particularity_absent_n,
           max(d.prior_override_count)                            AS prior_override_max,
           min(d.signer_rank)                                     AS min_signer_rank,
           max(d.signed_at)                                       AS last_signed_at
      FROM mainline.disposition d
     WHERE d.retracted_by IS NULL
     GROUP BY d.signer_sub, d.site_id
  ),
  t AS (SELECT count(*) AS group_count FROM base)
  SELECT base.signer_sub                AS signer_sub,
         base.site_id                   AS site_id,
         base.dispositions              AS dispositions,
         medians.median_deliberation_seconds AS median_deliberation_seconds,
         base.mechanism_absent_n        AS mechanism_absent_n,
         round(base.mechanism_absent_n::NUMERIC / base.dispositions, 4)
                                        AS mechanism_absent_share,
         base.emergency_override_n      AS emergency_override_n,
         base.accept_residual_n         AS accept_residual_n,
         base.floor_unmet_n             AS floor_unmet_n,
         base.countersigned_n           AS countersigned_n,
         base.evidence_opened_n         AS evidence_opened_n,
         base.stale_replay_n            AS stale_replay_n,
         base.blood_ancestry_n          AS blood_ancestry_n,
         base.mean_particularity        AS mean_particularity,
         base.particularity_absent_n    AS particularity_absent_n,
         base.prior_override_max        AS prior_override_max,
         base.min_signer_rank           AS min_signer_rank,
         base.last_signed_at            AS last_signed_at,
         -- Fail-closed completeness, in this view's own terms: a mean particularity taken
         -- over a population in which some rows have no particularity at all is a mean
         -- over a subset, and the reader is told rather than shown the subset's number.
         (base.particularity_absent_n = 0) AS measures_complete,
         t.group_count                  AS group_count,
         (t.group_count <= 25)          AS rows_complete
    FROM base
    JOIN medians
      ON medians.signer_sub = base.signer_sub
     AND medians.site_id    = base.site_id
    CROSS JOIN t
   ORDER BY base.dispositions DESC, base.signer_sub, base.site_id
   LIMIT 25;
