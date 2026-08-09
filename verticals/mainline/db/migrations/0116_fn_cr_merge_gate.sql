-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0116_fn_cr_merge_gate.sql
-- CREATE FUNCTION mainline.fn_cr_merge_gate() — the re-derivation, the time condition, and the certified null
--
-- MI: MI02, MI22
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: A gate that trusted its own counters would be a gate that a single bad UPDATE
--            disarms, so the completing transition re-derives the open obligation count
--            from the base tables and refuses when the derivation disagrees with the
--            projection. It refuses nothing a CHECK can refuse: a synthetic 23514 carries
--            no constraint name and the constraint name is the exhibit. What is left is
--            exactly what no CHECK can hold — a condition over now(), a condition over the
--            absence of a row, and a counter that was never computed at all.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0115_fn_merge_gate.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- SUBJECT: change_request (mainline.change_request), completing state
-- 'merged'. Welded to the table by migration
-- 0131_trg_cr_merge_gate.sql, which carries the WHEN clause that
-- restricts this function to the completing transition and keeps the trigger graph
-- acyclic and depth 1.
--
-- REFUSAL DEPTH, honestly stated. Every arm below is DEPTH 1 on its own: it is a
-- RAISE, and a RAISE is one mechanism. The depth-2 claim the conformance suite makes
-- for CF-01 and CF-31 is not made by this function — it is made by the counter's
-- CHECK (cr_gate_closed_when_merged) surviving when this trigger is disabled, and by
-- this trigger surviving when the CHECK is dropped. That claim is proved by the
-- unwelding matrix, not asserted here, and at runtime the CHECK is what fires
-- because this function deliberately declines to pre-empt it.
--
-- THE EXHIBIT for every refusal below is the fully-qualified name of this function
-- (mainline.fn_cr_merge_gate), because `diag.constraint_name` is empty for
-- P0001 (spec/errors.md §3.1). A client recovers it from the PL/pgSQL error context;
-- where the driver cannot supply it, `trappoint_core.errors` records that the
-- diagnosis was WEAKENED rather than silently inferring it.

CREATE FUNCTION mainline.fn_cr_merge_gate() RETURNS TRIGGER
LANGUAGE PLpgSQL AS $fn$
DECLARE
  v_subject   UUID;
  v_projected INT8;
  v_derived   INT8;
  v_unbacked  INT8;
BEGIN
  -- `(NEW).col`, not `NEW.col`. See the platform note in this file's template: the
  -- unparenthesised read form does not survive CREATE TRIGGER on v26.2.5.
  v_subject   := (NEW).cr_id;
  v_projected := (NEW).open_blocking;

  -- ── 1 · RE-DERIVE THE OPEN OBLIGATION COUNT FROM THE BASE TABLES ──────────────
  -- The projection is enforced, never trusted (rule P-2). An obligation is OPEN when
  -- no live disposition covers it, and "live" carries a time condition — `retracted_by
  -- IS NULL` is a fact a CHECK could hold, `expires_at > now()` is not.
  SELECT count(*) INTO v_derived
    FROM mainline.blocking_check bc
   WHERE bc.cr_id = v_subject
     AND NOT EXISTS (
           SELECT 1 FROM mainline.disposition d
            WHERE d.check_id = bc.check_id
              AND d.retracted_by IS NULL
              AND (d.expires_at IS NULL OR d.expires_at > now()));

  -- ── 2 · DRIFT AND TIME (CF-02, CF-03) ────────────────────────────────────────
  -- Only when the projection reads ZERO. If the counter is also non-zero then
  -- cr_gate_closed_when_merged refuses this write with its own name attached, and
  -- trading that named exhibit for an unnamed P0001 would be a strictly worse
  -- refusal (spec/errors.md §3.3, corollary).
  IF v_derived <> 0 AND v_projected = 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: merge refused by mainline.fn_cr_merge_gate'
                || ' — re-derived open obligation count is '
                || v_derived::STRING || ' while the projected counter reads zero';
  END IF;

  -- ── 3 · FAIL CLOSED ON AN ABSENT AUTHORITY-SOURCE ROW (CF-06) ────────────────
  -- Declared by this binding, not known to the substrate:
  --   authority mainline.clause_blame_current (clause_uuid, as_of_commit)
  --          <= cited (clause_uuid, commit_id)
  --   on_missing raise
  -- Absence of evidence refuses. The original bug was the other asymmetry: a stale
  -- closure refused while a missing one admitted, and the missing one is the case
  -- with physical consequences.
  SELECT count(*) INTO v_unbacked
    FROM mainline.cr_clause cited
   WHERE cited.cr_id = v_subject
     AND NOT EXISTS (
           SELECT 1 FROM mainline.clause_blame_current auth
            WHERE auth.clause_uuid = cited.clause_uuid
              AND auth.as_of_commit = cited.commit_id);
  IF v_unbacked <> 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'MAINLINE: merge refused by mainline.fn_cr_merge_gate'
                || ' — no authority-source row for '
                || v_unbacked::STRING || ' cited clause version(s)';
  END IF;

  -- ── 4 · THE CERTIFIED NULL — NOT RENDERED FOR THIS BINDING ───────────────────
  -- This arm reads mainline.boundary_certificate, which this binding does not
  -- declare and does not own (`emit_outbox = true`, ruling D9). Stored
  -- procedures and functions bind EARLY on v26.2, so naming an absent relation here
  -- would make this migration un-appliable rather than make it degrade — which is
  -- exactly why the switch is at RENDER time and the fallback is this committed
  -- comment a reviewer can read (ruling D5). Conformance case CF-53 carries
  -- `profiles = ["mainline"]` for the same reason.

  RETURN NEW;
END $fn$;
