-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0128h_trg_refuse_mutation_signing_credential.sql
-- CREATE TRIGGER append_only ON trappoint_ref.signing_credential
--
-- MI: MI01
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: Weld 9 of 11 in the append-only family: a 2029 signature must still verify in
--            2036, so the old key never leaves. UPDATE and DELETE are one trigger because a
--            record rewritten and a record deleted are the same event from the archive
--            point of view. Revoked privileges are cluster state that a restore does not
--            carry and that an incident is exactly the moment somebody widens; this weld
--            travels with the schema.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0120_triggers_projection.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- band: 0120-0129z · kernel/projection-triggers · RENDERED · statements: 1
-- requires: 0107 trappoint_ref.fn_refuse_mutation · trappoint_ref.signing_credential
-- sqlstate: P0001, on every UPDATE and every DELETE, for every role, forever.
-- forward-only; no .down.sql and no .up.sql (MR-5).

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON trappoint_ref.signing_credential
  FOR EACH ROW EXECUTE FUNCTION trappoint_ref.fn_refuse_mutation();
