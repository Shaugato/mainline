-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI18
-- I: I07
-- COUNSEL-GATED: no
-- RATIONALE: `pg_get_triggerdef()` snapshots this definition into `mainline_ops.schema_attestation` and thence into the custody ledger on every migration, so nobody can quietly weaken the gate that prevents quietly weakening τ.
--
-- migration:  0136_trg_recall_policy_anchored
-- band:       0136-0139z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- domain:     recall
-- statements: 1
-- invariants: MI18
-- source:     ARCHITECTURE.md §5.11 (S24) — replaces the `CHECK (true)` placeholder
-- requires:   0112 mainline.fn_recall_policy_anchored · 0081 mainline_meas.recall_run
-- sqlstate:   P0001
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- The weld. `pg_get_triggerdef()` snapshots this definition into
-- `mainline_ops.schema_attestation` and thence into the custody ledger on every migration, so
-- nobody can quietly weaken the gate that prevents quietly weakening τ.

CREATE TRIGGER recall_policy_anchored BEFORE INSERT ON mainline_meas.recall_run
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_recall_policy_anchored();
