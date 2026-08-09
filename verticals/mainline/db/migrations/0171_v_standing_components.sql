-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0171_v_standing_components.sql
-- CREATE VIEW mainline_qa.v_standing_components — a score, its arithmetic, and the signed
-- policy that authorised computing it
--
-- MI: MI28
-- I: I15
-- COUNSEL-GATED: yes
-- RATIONALE: SEC-3 permits a derived authority level about a named person only if it is a
--            precondition of a state transition the database enforces, computed from a
--            pre-committed signed customer policy that PREDATES the data it scores,
--            recomputable by a third party, and obtainable by the person scored. Conditions
--            (2) and (3) are what this view is for: it puts the policy instrument, its
--            approval date, its notice date and the score's own components on one row, so
--            that "recomputable from primary facts by a third party" is a query rather than
--            a promise.
--
-- migration:  0171_v_standing_components
-- domain:     datamodel / dm-views-rls
-- band:       0170-0179z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI28 — a bounded window means bounded, not merely present. `window_from` and
--                    `policy_effective_from` are carried together because the standing row's
--                    `within_policy` CHECK is the boundedness, and a reader who cannot see
--                    both cannot check it.
--             I15  — the allegation firewall. `mainline_meas.standing` is a MEASUREMENT-zone
--                    table, not a substrate table, and this view is in `mainline_qa`.
-- source:     ARCHITECTURE.md §17 (S14: v_standing_components lives in mainline_qa) ·
--             §11.5 (SEC-3, conditions 1-4) · §5.7 (standing, person_measure_policy) ·
--             correction S14, S18
-- requires:   0089 mainline_meas.standing · 0089 mainline_meas.person_measure_policy
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
--
-- ═════════════════════════════════════════════════════════════════════════════
-- M10 SHIPS INERT, AND THE INERTNESS IS ITSELF A DATED OBJECT
-- ═════════════════════════════════════════════════════════════════════════════
-- §11.5: M10 ships inert — W = 1.0 for every hazard class, i.e. quorum = one
-- signature = today's behaviour — with the inertness itself a dated object. So
-- on a shipped deployment this view returns rows in which `s` is 1.0 and nothing
-- downstream consumes it.
--
-- That is not a placeholder. An inert mechanism whose activation requires a
-- signed, notified, pre-dating customer policy row is a mechanism whose
-- activation is DISCOVERABLE and DATED. The alternative — leave the table out
-- until counsel answers — makes the activation a deployment, and a deployment
-- leaves no row.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- WHY THE POLICY JOIN IS INNER AND NOT LEFT
-- ═════════════════════════════════════════════════════════════════════════════
-- `standing.policy_id` is `NOT NULL REFERENCES person_measure_policy`, so the
-- join cannot drop a row that exists. Writing it as a LEFT JOIN would suggest a
-- standing score can exist without a policy, which is exactly the state SEC-3
-- makes unrepresentable and `within_policy` refuses with 23514. An INNER JOIN is
-- the shape that tells the truth about the constraint.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- WHY `components` IS RETURNED AS TEXT AND BOUNDED
-- ═════════════════════════════════════════════════════════════════════════════
-- The components object is the score's arithmetic and it is the whole point of
-- condition (3). It is also unbounded JSONB, and this view has a 10 KiB budget
-- across 25 rows. Returning `components::STRING` truncated to 400 characters
-- gives a reader the shape and the leading terms; the FULL object is obtained by
-- selecting the row from `mainline_meas.standing` directly, which the QA service
-- can do and which writes the same `profile_read` ledger entry.
--
-- `components_truncated` says which of the two happened, because a truncated
-- arithmetic that reads as complete is the same class of defect as a truncated
-- ancestry that reads as complete.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- WHAT THIS VIEW IS NOT
-- ═════════════════════════════════════════════════════════════════════════════
-- 1. IT IS NOT THE PERSON'S OWN DISCLOSURE PATH. SEC-3 condition (4) is served
--    by `mainline_qa.v_my_record` under the `subject_access` role (0172). This
--    view is the QA function's, under `quality_assurance`, and the two are
--    deliberately different objects with different scopes: one is scoped to
--    CURRENT_USER in its own body, the other is not scoped at all.
-- 2. IT IS NOT REACHABLE BY A SIGNER LATERALLY. `standing_blind` is RESTRICTIVE
--    `USING (false)` on the base table for the `signer` role — not "your own row
--    only", nothing at all — because M10's peer-prediction channel is defeated
--    by a participant who can see the scoring.
-- 3. IT IS NOT ON THE MCP SURFACE. No MCP service account is ever issued for
--    `mainline_qa`, on any tier, ever (S14).

CREATE VIEW mainline_qa.v_standing_components AS
  WITH base AS (
    SELECT st.actor_sub             AS actor_sub,
           st.hazard_class          AS hazard_class,
           st.window_from           AS window_from,
           st.s                     AS s,
           st.components            AS components,
           st.computed_at           AS computed_at,
           st.policy_effective_from AS policy_effective_from,
           pmp.policy_id            AS policy_id,
           pmp.measure_class        AS measure_class,
           pmp.instrument_title     AS instrument_title,
           pmp.instrument_sha256    AS instrument_sha256,
           pmp.approved_by_sub      AS approved_by_sub,
           pmp.approved_at          AS approved_at,
           pmp.notice_given_at      AS notice_given_at,
           pmp.notice_jurisdiction  AS notice_jurisdiction,
           pmp.adm_class_id         AS adm_class_id,
           pmp.effective_from       AS effective_from,
           pmp.effective_to         AS effective_to
      FROM mainline_meas.standing st
      JOIN mainline_meas.person_measure_policy pmp
        ON pmp.policy_id = st.policy_id
  ),
  t AS (SELECT count(*) AS group_count FROM base)
  SELECT base.actor_sub            AS actor_sub,
         base.hazard_class         AS hazard_class,
         base.window_from          AS window_from,
         base.s                    AS s,
         -- SEC-3 condition (3), bounded to fit the transport. See the block above.
         left(base.components::STRING, 400) AS components_head,
         (length(base.components::STRING) > 400) AS components_truncated,
         base.computed_at          AS computed_at,
         base.measure_class        AS measure_class,
         base.instrument_title     AS instrument_title,
         encode(base.instrument_sha256, 'hex') AS instrument_sha256_hex,
         base.approved_by_sub      AS approved_by_sub,
         base.approved_at          AS approved_at,
         base.notice_given_at      AS notice_given_at,
         base.notice_jurisdiction  AS notice_jurisdiction,
         base.adm_class_id         AS adm_class_id,
         base.effective_from       AS policy_effective_from,
         base.effective_to         AS policy_effective_to,
         -- SEC-3 condition (2), re-derived so a reader does not have to trust the CHECK:
         -- the policy predates the data it scores, and notice predates the policy taking
         -- effect. Both are `within_policy` and `notice_precedes_effect` restated as
         -- readable columns.
         (base.window_from >= base.policy_effective_from) AS scored_within_policy,
         (base.notice_given_at <= base.effective_from)    AS notice_preceded_effect,
         -- MI28: bounded means bounded. An open-ended policy is a real state and it is not
         -- the same state as a closed one, so it is reported rather than coalesced.
         (base.effective_to IS NOT NULL)                  AS policy_window_closed,
         (base.effective_to IS NULL OR base.window_from <= base.effective_to)
                                                          AS scored_before_policy_expiry,
         t.group_count             AS group_count,
         (t.group_count <= 25)     AS rows_complete
    FROM base CROSS JOIN t
   ORDER BY base.actor_sub, base.hazard_class, base.window_from DESC
   LIMIT 25;
