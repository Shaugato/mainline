-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0101_fn_check_materialised.sql
-- CREATE FUNCTION trappoint_ref.fn_check_materialised — a new obligation closes the gate and bumps the epoch
--
-- MI: MI02, MI07, MI30
-- I: I02, I03
-- COUNSEL-GATED: no
-- RATIONALE: PROJECT and PIN in one function: open_blocking + 1 closes a CHECK over a plain
--            scalar so the merge is refused for every writer forever, and gate_epoch + 1
--            moves the subject to a new (id, epoch) pair so the completion record composite
--            FK with ON UPDATE RESTRICT makes attaching a precursor to an issued subject
--            physically impossible. A precursor arriving after the merge raises P0001
--            rather than racing two structural refusals whose order is unassertable.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0101_fn_check_materialised.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- migration:  0101_fn_check_materialised
-- band:       0100-0109z · kernel/projection-triggers · RENDERED
-- statements: 1
-- invariants: MI02 / MI30 (a merged subject has zero open blocking checks — this function is the
--             half the database MAINTAINS; the counter CHECK is the half that REFUSES) ·
--             MI07 (no precursor may be attached to an issued subject)
-- source:     ARCHITECTURE.md §5.11 item 2 · §2.2 S4, S16 · docs/leads/kernel.md D9
-- requires:   trappoint_ref.blocking_check (0058) ·
--             trappoint_ref.permit with gate_epoch and open_blocking
--             trappoint_ref.change_request with gate_epoch and open_blocking
-- provides:   trappoint_ref.fn_check_materialised() — welded to blocking_check by 0121
-- sqlstate:   P0001 on a post-merge precursor and on a check naming no gated subject.
--             Structurally also 23514 (counter CHECK) and 23503 (epoch pin) — proved by the
--             unwelding suite, never claimed from runtime behaviour (finding S4).
-- forward-only; no .down.sql and no .up.sql (MR-5).
--
-- ACYCLICITY. AFTER INSERT on blocking_check. It writes the gated subject tables, and the only trigger on a gated subject table is the merge gate,
-- whose WHEN clause restricts it to the merge transition — so this UPDATE cannot re-enter.
-- Trigger depth contributed: 1.

CREATE FUNCTION trappoint_ref.fn_check_materialised() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_state trappoint_ref.subject_state;
BEGIN
  IF (NEW).permit_id IS NOT NULL THEN
    SELECT t.state INTO v_state
      FROM trappoint_ref.permit t
     WHERE t.permit_id = (NEW).permit_id
       FOR UPDATE;
    IF v_state IS NULL THEN
      RAISE EXCEPTION USING ERRCODE='P0001',
        MESSAGE='TRAPPOINT_REF: no permit row for this blocking check — the gate has no subject to close';
    END IF;
    IF v_state = 'merged' THEN
      RAISE EXCEPTION USING ERRCODE='P0001',
        MESSAGE='TRAPPOINT_REF: precursor arrived after issue — use the post-issue recall path';
    END IF;
    UPDATE trappoint_ref.permit
       SET open_blocking = open_blocking + 1,
           gate_epoch = gate_epoch + 1
     WHERE permit_id = (NEW).permit_id;
  ELSIF (NEW).cr_id IS NOT NULL THEN
    SELECT t.state INTO v_state
      FROM trappoint_ref.change_request t
     WHERE t.cr_id = (NEW).cr_id
       FOR UPDATE;
    IF v_state IS NULL THEN
      RAISE EXCEPTION USING ERRCODE='P0001',
        MESSAGE='TRAPPOINT_REF: no change_request row for this blocking check — the gate has no subject to close';
    END IF;
    IF v_state = 'merged' THEN
      RAISE EXCEPTION USING ERRCODE='P0001',
        MESSAGE='TRAPPOINT_REF: precursor arrived after issue — use the post-issue recall path';
    END IF;
    UPDATE trappoint_ref.change_request
       SET open_blocking = open_blocking + 1,
           gate_epoch = gate_epoch + 1
     WHERE cr_id = (NEW).cr_id;
  ELSE
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='TRAPPOINT_REF: a blocking check names no gated subject — an obligation that blocks nothing is not an obligation';
  END IF;

  -- Ruling D9. This binding declares emit_outbox = false, so no changefeed row is written and
  -- this file names no relation the binding does not own.
  RETURN NEW;
END $$;
