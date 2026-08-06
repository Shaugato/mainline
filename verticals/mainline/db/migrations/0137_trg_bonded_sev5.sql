-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0137_trg_bonded_sev5
-- domain:     recall
-- statements: 1
-- invariants: MI16
-- source:     ARCHITECTURE.md §5.11 · §5.7 (S10)
-- requires:   0113 mainline.fn_bonded_sev5 · 0058 mainline.blocking_check · 0081 recall_run
-- sqlstate:   23514 (via `bonded_fatalities_all_blocking` on the row this trigger maintains)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- AFTER INSERT, not BEFORE: the check row must be committed to before the run's accounting
-- moves, and the counter belongs to a different table, so there is nothing to project onto NEW.
--
-- ORDERING AGAINST `check_materialised` (§5.11 #2, the other AFTER INSERT trigger on this
-- table) IS NOT A CORRECTNESS DEPENDENCY, and that is deliberate. Both fire in the same
-- transaction, so if `check_materialised` RAISEs — "precursor arrived after issue" — this
-- counter's UPDATE is unwound with it, in either firing order. PostgreSQL fires row triggers in
-- name order; CockroachDB's ordering guarantee is NOT verified here and nothing in this domain
-- is written to depend on it.

CREATE TRIGGER bonded_sev5 AFTER INSERT ON mainline.blocking_check
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_bonded_sev5();
