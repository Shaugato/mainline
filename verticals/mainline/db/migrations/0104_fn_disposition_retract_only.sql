-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0104_fn_disposition_retract_only.sql
-- CREATE FUNCTION mainline.fn_disposition_retract_only — one column, one direction, once
--
-- MI: MI01, MI07
-- I: I01, I03
-- COUNSEL-GATED: no
-- RATIONALE: The single permitted UPDATE in the operational zone. The comparison is the
--            whole row minus retracted_by rather than a list of six named columns, because
--            a guard that names six of forty is a guard whose completeness depends on
--            nobody adding a forty-first, and this table gains columns whenever the design
--            learns something. Retraction re-opens the obligation and bumps the epoch, so a
--            retraction after issue is refused by the epoch pin rather than by a policy
--            nobody can point at.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0104_fn_disposition_retract_only.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- migration:  0104_fn_disposition_retract_only
-- band:       0100-0109z · kernel/projection-triggers · RENDERED
-- statements: 1
-- invariants: MI01 (evidentiary tables are append-only — this is the one stated exception, and
--             stating it narrowly is what keeps it an exception) · MI07 (no precursor may be
--             attached to an issued subject: the epoch bump routes a post-issue retraction into
--             the pin's ON UPDATE RESTRICT)
-- source:     ARCHITECTURE.md §5.11 item 10 · §5.5 · docs/leads/kernel.md D2
-- requires:   mainline.disposition (0066) ·
--             mainline.permit (open_blocking, gate_epoch)
--             mainline.change_request (open_blocking, gate_epoch)
-- provides:   mainline.fn_disposition_retract_only() — welded to disposition by 0124
-- sqlstate:   P0001 on a re-retraction, on an un-retraction, and on any other column changing.
--             23503 on the epoch pin when the subject has already merged — which is the point.
-- forward-only; no .down.sql and no .up.sql (MR-5).
--
-- ACYCLICITY. BEFORE UPDATE on disposition; writes the gated subject tables, whose only trigger
-- is the merge gate restricted by its WHEN clause to the merge transition. Trigger depth
-- contributed: 1.

CREATE FUNCTION mainline.fn_disposition_retract_only() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
BEGIN
  -- One direction, once. A row already retracted cannot be retracted again, and a retraction
  -- cannot be undone by writing NULL back.
  IF (OLD).retracted_by IS NOT NULL OR (NEW).retracted_by IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: dispositions are append-only except for a single retraction';
  END IF;

  -- The whole row minus the one permitted column, compared as data. Exhaustive by construction.
  IF (to_jsonb(NEW) - 'retracted_by') IS DISTINCT FROM (to_jsonb(OLD) - 'retracted_by') THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: only retracted_by may change on a disposition';
  END IF;

  -- The gate RE-OPENS, and the epoch moves with it. Read from OLD: the subject columns are
  -- projections written at insert and the guard above has just proved NEW agrees with OLD, so
  -- OLD is the side that cannot have been influenced by this statement.
  IF (OLD).permit_id IS NOT NULL THEN
    UPDATE mainline.permit
       SET open_blocking = open_blocking + 1,
           gate_epoch = gate_epoch + 1
     WHERE permit_id = (OLD).permit_id;
  ELSIF (OLD).cr_id IS NOT NULL THEN
    UPDATE mainline.change_request
       SET open_blocking = open_blocking + 1,
           gate_epoch = gate_epoch + 1
     WHERE cr_id = (OLD).cr_id;
  ELSE
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: a disposition names no gated subject — nothing to re-open';
  END IF;
  RETURN NEW;
END $$;
