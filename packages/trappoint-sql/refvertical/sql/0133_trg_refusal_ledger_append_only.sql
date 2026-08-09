-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0133_trg_refusal_ledger_append_only.sql
-- CREATE TRIGGER trg_refusal_ledger_append_only ON trappoint_ref.refusal_ledger
--
-- MI: MI01
-- I: I01, I14
-- COUNSEL-GATED: no
-- RATIONALE: One trigger over all three write events, because append-only that only covers
--            UPDATE is not append-only. The same firing also validates the payload on
--            INSERT, so the ledger cannot accept a row whose reason set is not a reason
--            set. Revoked grants are the other mechanism and neither is trusted alone: the
--            unwelding harness disables this trigger and asserts the write still fails.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0119a_fn_explain_refusal.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- BEFORE, not AFTER: an AFTER trigger refuses a write the database has already performed
-- and then unwinds it, which is correct and is also a story nobody should have to tell.
--
-- FOR EACH ROW: a statement-level trigger cannot see the payload it is meant to check.

CREATE TRIGGER trg_refusal_ledger_append_only
  BEFORE INSERT OR UPDATE OR DELETE ON trappoint_ref.refusal_ledger
  FOR EACH ROW EXECUTE FUNCTION trappoint_ref.fn_refusal_ledger_guard();
