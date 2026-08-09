-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0172_v_my_record.sql
-- CREATE VIEW mainline_qa.v_my_record — SEC-3 condition (4), which is what stops a score
-- being an allegation
--
-- MI: MI27, MI28
-- I: I15
-- COUNSEL-GATED: yes
-- RATIONALE: A score you compute about a person, use against them, and refuse to show them is
--            the definition of an allegation. A score you compute, use, disclose on request,
--            and derive from their employer's own signed policy is an OPERATING AUTHORITY —
--            the same species of object as a high-voltage switching ticket, and juries
--            understand those. This view is the disclosure, and it exists so that condition
--            (4) is a database object rather than a support process.
--
-- migration:  0172_v_my_record
-- domain:     datamodel / dm-views-rls
-- band:       0170-0179z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI27 — a disposition's identity, rank, org and competency are projections of
--                    `person`. The record disclosed here is therefore the record the system
--                    actually acted on, not a re-narration of it.
--             MI28 — a bounded window means bounded. The policy window is disclosed with the
--                    score, because a score without its authorising window is not derivable.
--             I15  — the allegation firewall, discharged in the only direction that makes it
--                    survivable: the subject can read their own side of it.
-- source:     ARCHITECTURE.md §11.5 (SEC-3 condition 4) · §11.2 (`subject_access` reads
--             `mainline_qa.v_my_record`, RLS-scoped to CURRENT_USER) · §5.7 ·
--             verticals/mainline/db/GRANTS.yaml (`subject_access_views`)
-- requires:   0089 mainline_meas.standing · 0089 mainline_meas.person_measure_policy ·
--             0066 mainline.disposition
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
--
-- ═════════════════════════════════════════════════════════════════════════════
-- THE SCOPING IS A VIEW-BODY PREDICATE, NOT AN RLS POLICY, AND THAT IS NOT A
-- WEAKER CONTROL — IT IS THE ONLY EXPRESSIBLE ONE
-- ═════════════════════════════════════════════════════════════════════════════
-- §11.2's row reads "`mainline_qa.v_my_record` (RLS-scoped to CURRENT_USER)".
-- Verified against the v26.2 row-level-security reference: **policies can only
-- be defined directly on tables, not on views.** There is no `CREATE POLICY … ON
-- mainline_qa.v_my_record` to write.
--
-- Worse, the base tables' own policies would be evaluated as THIS VIEW'S OWNER,
-- not as the person reading it — v26.2 evaluates a view's underlying access with
-- the view owner's privileges unless the view is created `WITH
-- (security_invoker)`. So even a per-person policy on `mainline_meas.standing`
-- would not scope this view; it would be evaluated against `mainline_owner` and
-- return everybody.
--
-- The scoping is therefore `WHERE … = current_user` in the view body. Three
-- things make that a real control rather than a comment:
--
--   1. IT IS THE SAME IDIOM AS EVERY OTHER SCOPE IN THIS SCHEMA. §11.3's
--      documented-safe shape is `USING (col = CURRENT_USER)` over a denormalised
--      role-name token. This is that predicate, in the only place it can be
--      written for a view.
--   2. `current_user` IS NOT CLIENT-SETTABLE. It changes only via `SET ROLE`,
--      which succeeds only for roles the session has been granted, and the grant
--      graph is alterable only by the provisioning service account. A session
--      variable would be client-settable and would degrade this to an
--      application-cooperative control.
--   3. THE DEPLOYMENT CONTRACT IS EXPLICIT. The provisioning service account
--      creates ONE SQL ROLE PER PERSON, NAMED WITH THAT PERSON'S `signer_sub`,
--      and grants `subject_access` TO it. The person queries AS their own role
--      and INHERITS the privilege; they never `SET ROLE subject_access`, because
--      doing so would make `current_user` equal to `subject_access` and this
--      view would correctly return nothing. That is the same construction
--      GRANTS.yaml records for `site_reader`: "site_reader itself is the
--      privilege carrier; the per-site role is the scope token."
--
-- If the deployment ever needs invoker semantics on the base tables as well,
-- v26.2's `CREATE VIEW … WITH (security_invoker)` is the lever (C2). It is not
-- used here, because the scoping this view needs is expressible without it and
-- an unexercised option is not a dependency worth taking.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- THIS READ IS LEDGERED LIKE EVERY OTHER READ OF THIS SCHEMA
-- ═════════════════════════════════════════════════════════════════════════════
-- §11.5: every SELECT against `mainline_qa` writes a `profile_read` ledger entry.
-- That applies to the subject's own read of their own record, and it should:
-- the person is entitled to know that their disclosure request is itself on the
-- record, and the organisation is entitled to be able to prove it answered.
-- The enforcement is the QA/disclosure service's transaction, not this view —
-- see the corresponding block in 0170, which states the same limitation in the
-- same words rather than implying a mechanism a view cannot have.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- WHAT THIS VIEW IS NOT
-- ═════════════════════════════════════════════════════════════════════════════
-- 1. IT IS NOT A PRIVACY-ACT ACCESS REQUEST IN FULL. It discloses the DERIVED
--    measures and their authorising policy — the objects SEC-3 (S) governs. A
--    full access request also reaches events, dispositions and receipts, and it
--    is answered by a reviewed process, not by one view.
-- 2. IT DOES NOT LET A PERSON EDIT THEIR RECORD. `subject_access` holds SELECT
--    and nothing else, on one object, forever (GRANTS.yaml enumerates it rather
--    than wildcarding the schema precisely so that a view added later is not
--    silently disclosed).
-- 3. IT IS NOT SCOPED BY SITE. A person's record is theirs across every site
--    they have signed at; scoping it by site would let an employer hide the part
--    of a person's own record that happened somewhere else.

CREATE VIEW mainline_qa.v_my_record AS
  WITH me AS (
    SELECT st.actor_sub             AS actor_sub,
           st.hazard_class          AS hazard_class,
           st.window_from           AS window_from,
           st.s                     AS s,
           st.components            AS components,
           st.computed_at           AS computed_at,
           pmp.measure_class        AS measure_class,
           pmp.instrument_title     AS instrument_title,
           pmp.instrument_sha256    AS instrument_sha256,
           pmp.approved_by_sub      AS approved_by_sub,
           pmp.approved_at          AS approved_at,
           pmp.notice_given_at      AS notice_given_at,
           pmp.notice_sha256        AS notice_sha256,
           pmp.notice_jurisdiction  AS notice_jurisdiction,
           pmp.adm_class_id         AS adm_class_id,
           pmp.effective_from       AS policy_effective_from,
           pmp.effective_to         AS policy_effective_to
      FROM mainline_meas.standing st
      JOIN mainline_meas.person_measure_policy pmp
        ON pmp.policy_id = st.policy_id
     -- THE SCOPE. See the block above: this is the only place a view can carry it.
     WHERE st.actor_sub = current_user
  ),
  mine AS (
    SELECT count(*)                                       AS dispositions_signed,
           count(*) FILTER (WHERE d.retracted_by IS NOT NULL) AS dispositions_retracted,
           max(d.signed_at)                               AS last_signed_at,
           max(d.prior_override_count)                    AS prior_override_max
      FROM mainline.disposition d
     WHERE d.signer_sub = current_user
  ),
  t AS (SELECT count(*) AS group_count FROM me)
  SELECT me.actor_sub               AS actor_sub,
         me.hazard_class            AS hazard_class,
         me.window_from             AS window_from,
         me.s                       AS score,
         -- The subject gets the arithmetic IN FULL and untruncated. Condition (3) is
         -- "recomputable from primary facts by a third party" and condition (4) is the
         -- subject's own access; a truncated derivation would satisfy neither, and the
         -- 25-row / 10 KiB transport budget that shapes `mainline_audit` does not apply
         -- here — no MCP account reaches this schema, on any tier, ever (S14).
         me.components              AS components,
         me.computed_at             AS computed_at,
         me.measure_class           AS measure_class,
         me.instrument_title        AS authorising_policy_title,
         encode(me.instrument_sha256, 'hex') AS authorising_policy_sha256_hex,
         me.approved_by_sub         AS approved_by_sub,
         me.approved_at             AS approved_at,
         me.notice_given_at         AS notice_given_at,
         encode(me.notice_sha256, 'hex')     AS notice_sha256_hex,
         me.notice_jurisdiction     AS notice_jurisdiction,
         me.adm_class_id            AS adm_class_id,
         me.policy_effective_from   AS policy_effective_from,
         me.policy_effective_to     AS policy_effective_to,
         mine.dispositions_signed   AS dispositions_signed,
         mine.dispositions_retracted AS dispositions_retracted,
         mine.last_signed_at        AS last_signed_at,
         mine.prior_override_max    AS prior_override_max,
         (me.window_from >= me.policy_effective_from) AS scored_within_policy,
         (me.notice_given_at <= me.policy_effective_from) AS notice_preceded_effect,
         t.group_count              AS group_count,
         (t.group_count <= 25)      AS rows_complete
    FROM me CROSS JOIN mine CROSS JOIN t
   ORDER BY me.window_from DESC, me.hazard_class
   LIMIT 25;
