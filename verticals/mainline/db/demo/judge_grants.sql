-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
--
-- ============================================================================================
-- THE JUDGE READ SURFACE — a closed list, reviewable in one screen
-- ============================================================================================
--
-- Owner: w10-judge-and-acceptance.  Applied by scripts/deploy/judge_access.py.
-- Measured against CockroachDB CCL v26.2.5, local single node, database
-- `w_w10_judge_and_acceptance`, migration chain 271/271 applied, on 2026-08-10.
--
-- This file is the *reviewable* half of judge access. It is a closed list of fourteen views
-- and four schema traversals, and nothing else. `scripts/deploy/judge_access.py` is the
-- *evidential* half: it applies this file and then connects AS the login and asserts, from the
-- other side, what can and cannot be read. A grant is a claim about intent; a 42501 is
-- evidence about behaviour, and only the second one is worth publishing to a stranger.
--
-- --------------------------------------------------------------------------------------------
-- WHY EVERY VIEW IS NAMED, AND `ON ALL TABLES IN SCHEMA` APPEARS NOWHERE
-- --------------------------------------------------------------------------------------------
-- `GRANT SELECT ON ALL TABLES IN SCHEMA mainline_audit` would silently pick up whatever a later
-- migration adds to that schema. The whole point of a credential handed to an anonymous judge is
-- that its reach is a closed list somebody reviewed. Fourteen lines that a reviewer can read is
-- worth more than one line that a reviewer has to trust.
--
-- The list is identical to `AUDIT_VIEWS` in scripts/deploy/cloud_roles.py (w2-cloud-database).
-- Two copies is one too many and judge_access.py asserts they agree, so a view added to one and
-- not the other is a failed run rather than a silent divergence.
--
-- --------------------------------------------------------------------------------------------
-- THE FOUR SCHEMA GRANTS THAT LOOK WRONG AND ARE NOT — MEASURED, NOT ASSUMED
-- --------------------------------------------------------------------------------------------
-- A view evaluates its underlying query with its OWNER's table privileges. That is true here and
-- is the fourth trap RLS-MATRIX.yaml names. But the SCHEMA USAGE check is made against the
-- INVOKER regardless. Measured on this platform, in this order:
--
--   with USAGE on mainline_audit only:
--     SELECT count(*) FROM mainline_audit.v_open_gate_summary
--       -> 42501  user does not have USAGE privilege on schema mainline
--
--   with USAGE additionally on mainline, mainline_meas, mainline_ops:
--     SELECT count(*) FROM mainline_audit.v_open_gate_summary   -> OK, rows=1
--     SELECT count(*) FROM mainline.permit
--       -> 42501  user does not have SELECT privilege on relation permit
--
-- So the judge login needs USAGE on the schemas its views TRAVERSE, and gets no table privilege
-- in any of them. USAGE is the right to NAME a schema; it is not the right to read anything in
-- it, and the second probe is the evidence rather than the assurance.
--
-- `mainline_qa` is absent from that list and always will be. Without USAGE the schema is not even
-- nameable, which is a strictly stronger position than a revoked SELECT — the login cannot
-- discover what it is missing. GRANTS.yaml S14 requires exactly this, and
-- verticals/mainline/demo/judge/PACK.md's own envelope names `mainline_qa` as never issued to any
-- MCP account on any tier. Measured as the judge login: 42501, no USAGE privilege on schema
-- mainline_qa.
--
-- --------------------------------------------------------------------------------------------
-- ROW-LEVEL SECURITY, AND THE FAILURE THAT LOOKS LIKE SUCCESS
-- --------------------------------------------------------------------------------------------
-- Four tables carry FORCE ROW LEVEL SECURITY on this chain — measured from pg_class, not read
-- off a document: mainline.permit, mainline.change_request, mainline.disposition and
-- mainline_meas.standing. FORCE means the owner is NOT exempt, so every mainline_audit view over
-- those tables returns ZERO ROWS unless the view's owner carries a policy of its own.
--
-- Zero rows is the worst possible outcome for an audit surface handed to a judge: it is
-- indistinguishable from "nothing is wrong". The migration chain answers it with `view_owner_read`
-- (RLS-MATRIX.yaml), one PERMISSIVE SELECT policy per forced table granted to the view owner.
--
-- This file therefore grants nothing to work around RLS, and judge_access.py refuses to certify a
-- run in which every view came back empty. Measured as the judge login on the scratch database:
-- 14 of 14 views readable, 6 of them non-empty. A view that is empty because the seed is small is
-- fine; fourteen empty views means the policy is gone, and that is a red run.
--
-- --------------------------------------------------------------------------------------------
-- TWO THINGS THE APPLIER DOES THAT THIS FILE CANNOT
-- --------------------------------------------------------------------------------------------
-- 1. `@DATABASE@` below is substituted by judge_access.py with the database being provisioned.
--    CockroachDB v26.2.5 parses a PL/pgSQL `DO` block but refuses a dynamic statement inside it —
--    `0A000 unimplemented: PL/pgSQL EXECUTE of a dynamic SQL string is not yet supported` — so
--    `format('GRANT CONNECT ON DATABASE %I', current_database())` is not available on this
--    platform. A token substituted by the applier is honest about being a token; a hard-coded
--    database name would be a file that silently grants on the wrong database.
--
-- 2. The `mainline_meas.external_attestation` grant at the bottom is expected to SKIP.
--    Measured 2026-08-10: that table HAS NO PRODUCER MIGRATION anywhere in the chain —
--    `grep -rl "CREATE TABLE.*external_attestation" verticals/mainline/db/migrations/` returns
--    nothing, and the only file that names it is 0089b_standing.sql. GRANTS.yaml grants INSERT on
--    it "since 0089" and verticals/mainline/demo/judge/FALLBACK.md builds its entire
--    Managed-MCP write-surface argument on it. It does not exist.
--
--    A GRANT against an absent relation is `42P01 cannot determine the target type`, which would
--    abort a whole-file run. GRANTS.yaml's own contract for `grants apply` covers this: a row
--    whose object is absent is SKIPPED WITH A WARNING, never an error, because a cluster migrated
--    only part-way must still be grantable. judge_access.py implements that rule, so the statement
--    stays in this file, visibly, and its skip is reported. Deleting it would hide the gap; leaving
--    it unguarded would break the file. The consequence, stated plainly: **the judge login has no
--    write surface at all on this deployment.** That is a stronger position than the one the
--    documents describe, and it is the true one.
--
-- --------------------------------------------------------------------------------------------
-- IDEMPOTENCE, AND WHY THE REVOCATIONS ARE AT THE END
-- --------------------------------------------------------------------------------------------
-- Every statement is safe to re-run. The revocations are re-asserted on every run because drift
-- is additive: a privilege granted by hand during an incident survives the next deploy unless
-- something takes it away, and the only reliable moment to take it away is the moment the rest of
-- the surface is being asserted.
--
-- NO PASSWORD APPEARS IN THIS FILE. The login is created here with LOGIN and no credential;
-- judge_access.py sets the password out of band and writes it to SSM. A password in a committed
-- SQL file is a published password.
-- ============================================================================================


-- ── 1. the login ─────────────────────────────────────────────────────────────────────────────
-- Created without a password on purpose (see the header). On the insecure local node a password
-- cannot be set at all — `28P01 setting or updating a password is not supported in insecure mode`
-- — so a file that tried would be a file that only works on Cloud.
CREATE ROLE IF NOT EXISTS mainline_judge WITH LOGIN;

GRANT CONNECT ON DATABASE @DATABASE@ TO mainline_judge;


-- ── 2. schema traversal ──────────────────────────────────────────────────────────────────────
-- mainline_audit is where the views live. The other three are traversed BY those views and carry
-- no table privilege whatsoever. See the header for the measurement that forced this.
GRANT USAGE ON SCHEMA mainline_audit TO mainline_judge;
GRANT USAGE ON SCHEMA mainline      TO mainline_judge;
GRANT USAGE ON SCHEMA mainline_meas TO mainline_judge;
GRANT USAGE ON SCHEMA mainline_ops  TO mainline_judge;


-- ── 3. the fourteen views, by name ───────────────────────────────────────────────────────────
-- Every object in mainline_audit is a view shaped to a bounded row count and payload; GRANTS.yaml
-- §6 records that as the reason the audit schema is safe to expose at all. Ten of these fourteen
-- are the source of a question in verticals/mainline/demo/judge/QUESTIONS.yaml.
GRANT SELECT ON TABLE mainline_audit.v_agent_actions                  TO mainline_judge;  -- Q09
GRANT SELECT ON TABLE mainline_audit.v_blame_coverage                 TO mainline_judge;  -- Q03
GRANT SELECT ON TABLE mainline_audit.v_cbm_ledger                     TO mainline_judge;
GRANT SELECT ON TABLE mainline_audit.v_changefeed_health              TO mainline_judge;
GRANT SELECT ON TABLE mainline_audit.v_disposition_coverage           TO mainline_judge;  -- Q04
GRANT SELECT ON TABLE mainline_audit.v_fixity_coverage                TO mainline_judge;  -- Q08
GRANT SELECT ON TABLE mainline_audit.v_gate_latency_daily             TO mainline_judge;
GRANT SELECT ON TABLE mainline_audit.v_ledger_health                  TO mainline_judge;  -- Q07
GRANT SELECT ON TABLE mainline_audit.v_open_gate_summary              TO mainline_judge;  -- Q01
GRANT SELECT ON TABLE mainline_audit.v_recall_conservation            TO mainline_judge;  -- Q06
GRANT SELECT ON TABLE mainline_audit.v_silence_summary                TO mainline_judge;  -- Q05, Q05F
GRANT SELECT ON TABLE mainline_audit.v_txn_restart_daily              TO mainline_judge;
GRANT SELECT ON TABLE mainline_audit.v_unused_indexes                 TO mainline_judge;
GRANT SELECT ON TABLE mainline_audit.v_weakenings_without_disposition TO mainline_judge;  -- Q02


-- ── 4. the one write, which is expected to skip ──────────────────────────────────────────────
-- See the header. This relation has no producer migration. The applier reports the skip; it does
-- not hide it, and it does not invent the table.
GRANT INSERT ON TABLE mainline_meas.external_attestation TO mainline_judge;


-- ── 5. the revocations, re-asserted every run ────────────────────────────────────────────────
-- Drift is additive. These are not redundant with the absence of a grant above: they undo a
-- privilege somebody added by hand between deploys.
--
-- mainline_qa first, because it is the one that must never be reachable (GRANTS.yaml S14).
REVOKE ALL ON SCHEMA mainline_qa FROM mainline_judge;
REVOKE ALL ON ALL TABLES IN SCHEMA mainline_qa FROM mainline_judge;

-- The three traversed schemas: the login may NAME them so its views can resolve, and may read
-- nothing in them. Measured as the judge login: SELECT on mainline.permit is 42501 after this.
REVOKE ALL ON ALL TABLES IN SCHEMA mainline      FROM mainline_judge;
REVOKE ALL ON ALL TABLES IN SCHEMA mainline_meas FROM mainline_judge;
REVOKE ALL ON ALL TABLES IN SCHEMA mainline_ops  FROM mainline_judge;

-- Re-assert the audit surface after the blanket revocations above, because a REVOKE ALL on a
-- schema the judge legitimately reads would otherwise be order-dependent. mainline_audit is not
-- in the revocation list, so this is belt and braces rather than a repair — but a file whose
-- correctness depends on a reader noticing that mainline_audit is absent from a list is a file
-- that will be broken by the next person who adds a line to the list.
GRANT USAGE ON SCHEMA mainline_audit TO mainline_judge;
