-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0103_fn_disposition_close.sql
-- CREATE FUNCTION trappoint_ref.fn_disposition_close — one signed disposition closes exactly one obligation
--
-- MI: MI02, MI29, MI30
-- I: I02, I10
-- COUNSEL-GATED: no
-- RATIONALE: The mirror of the materialisation trigger, and deliberately asymmetric:
--            closing decrements the obligation counter and does NOT bump the epoch, because
--            the epoch pin exists to stop a NEW obligation attaching to a completed
--            transition and a disposition is not one. The reading-rate floor is priced
--            rather than refused — it moves a counter whose CHECK admits a countersignature
--            — and an emergency override writes a ledger row here rather than in the
--            caller, because the count and the row must come from the same mechanism or
--            neither is evidence.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0103_fn_disposition_close.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- migration:  0103_fn_disposition_close
-- band:       0100-0109z · kernel/projection-triggers · RENDERED
-- statements: 1
-- invariants: MI02 / MI30 (the counter half) · MI29 (overrides escalate against the person
--             across permits, with no ceiling)
-- source:     ARCHITECTURE.md §5.11 item 4 · §2.2 S8, S19 · docs/leads/kernel.md D2, D4
-- requires:   trappoint_ref.disposition (0066) · trappoint_ref.override_ledger (0068) ·
--             trappoint_ref.permit (open_blocking, unmet_floor_count, countersigned_count)
--             trappoint_ref.change_request (open_blocking)
-- provides:   trappoint_ref.fn_disposition_close() — welded to disposition by 0123
-- sqlstate:   P0001 when the disposition names no gated subject. 23514 on the counter
--             non-negativity CHECK if a disposition were ever closed twice.
-- forward-only; no .down.sql and no .up.sql (MR-5).
--
-- COLUMN CONTRACT THIS FILE ASSUMES OF `override_ledger` (ruling D2): site_id, signer_sub,
-- subject_kind, permit_id, cr_id, disposition_id — with the two subject-id columns
-- NULLABLE and constrained in pairs, exactly as `blocking_check` and `disposition` are.
--
-- ACYCLICITY. AFTER INSERT on disposition; writes the gated subject tables and override_ledger.
-- override_ledger carries no trigger but the append-only guard (0128 family), which fires on
-- UPDATE and DELETE only. Trigger depth contributed: 1.

CREATE FUNCTION trappoint_ref.fn_disposition_close() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
BEGIN
  IF (NEW).permit_id IS NOT NULL THEN
    UPDATE trappoint_ref.permit
       SET open_blocking = open_blocking - 1
           -- Finding S19. Positive polarity, so NOT of it is what is counted.
         , unmet_floor_count = unmet_floor_count + (NOT (NEW).reading_floor_met)::INT8
         , countersigned_count =
             countersigned_count + ((NEW).countersigner_credential_id IS NOT NULL)::INT8
     WHERE permit_id = (NEW).permit_id;
  ELSIF (NEW).cr_id IS NOT NULL THEN
    UPDATE trappoint_ref.change_request
       SET open_blocking = open_blocking - 1
     WHERE cr_id = (NEW).cr_id;
  ELSE
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='TRAPPOINT_REF: a disposition names no gated subject — nothing to close';
  END IF;

  -- Finding S8. The ladder is site- and signer-scoped and monotone ACROSS subjects; there is no
  -- ceiling and no per-subject reset, because a reset is a bypass with a schedule.
  IF (NEW).kind = 'emergency_override' THEN
    INSERT INTO trappoint_ref.override_ledger
                (site_id, signer_sub, subject_kind, permit_id, cr_id, disposition_id)
         VALUES ((NEW).site_id, (NEW).signer_sub, (NEW).subject_kind,
                 (NEW).permit_id, (NEW).cr_id, (NEW).disposition_id);
  END IF;
  RETURN NEW;
END $$;
