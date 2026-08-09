-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0128d_trg_refuse_mutation_exposure_receipt.sql
-- CREATE TRIGGER append_only ON mainline.exposure_receipt
--
-- MI: MI01
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: Weld 5 of 11 in the append-only family: what the system showed, and when the
--            SERVER showed it. UPDATE and DELETE are one trigger because a record rewritten
--            and a record deleted are the same event from the archive point of view.
--            Revoked privileges are cluster state that a restore does not carry and that an
--            incident is exactly the moment somebody widens; this weld travels with the
--            schema.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0120_triggers_projection.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- band: 0120-0129z · kernel/projection-triggers · RENDERED · statements: 1
-- requires: 0107 mainline.fn_refuse_mutation · mainline.exposure_receipt
-- sqlstate: P0001, on every UPDATE and every DELETE, for every role, forever.
-- forward-only; no .down.sql and no .up.sql (MR-5).

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON mainline.exposure_receipt
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_refuse_mutation();
