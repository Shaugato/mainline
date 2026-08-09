-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0128j_trg_refuse_mutation_clause_blame_closure.sql
-- CREATE TRIGGER append_only ON trappoint_ref.clause_blame_closure
--
-- MI: MI01
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: Weld 11 of 11 in the append-only family: MI26 and finding S2: the one UPDATE
--            that would launder every ancestry gate at once. UPDATE and DELETE are one
--            trigger because a record rewritten and a record deleted are the same event
--            from the archive point of view. Revoked privileges are cluster state that a
--            restore does not carry and that an incident is exactly the moment somebody
--            widens; this weld travels with the schema.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0120_triggers_projection.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- band: 0120-0129z · kernel/projection-triggers · RENDERED · statements: 1
-- requires: 0107 trappoint_ref.fn_refuse_mutation · trappoint_ref.clause_blame_closure
-- sqlstate: P0001, on every UPDATE and every DELETE, for every role, forever.
-- forward-only; no .down.sql and no .up.sql (MR-5).

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON trappoint_ref.clause_blame_closure
  FOR EACH ROW EXECUTE FUNCTION trappoint_ref.fn_refuse_mutation();
