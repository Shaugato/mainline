-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0119a_fn_explain_refusal.sql
-- CREATE FUNCTION trappoint.explain_refusal — the declarative decomposition, one round trip
--
-- MI: MI02, MI11, MI07
-- I: I14, I02, I10
-- COUNSEL-GATED: no
-- RATIONALE: A gate that only says no gets routed around, and an invariant that is routed
--            around is not an invariant. This function maps a refused constraint to the
--            projected counter behind it and resolves that counters witness rows, which ARE
--            the minimal unsatisfiable subset for every single-counter refusal. It is
--            produced by the same engine that produced the refusal, so the explanation
--            cannot disagree with it. Where the counter is non-zero and no witness
--            resolves, it raises on drift rather than emit a plausible reason set.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0119a_fn_explain_refusal.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- SIGNATURE. `(subject_kind, subject_id, constraint_name)` is the specified call
-- (spec/invariants/I14-minimal-refusal.md) and it is the three-argument form. The fourth
-- parameter carries what the DATABASE cannot know because the attempt was rolled back:
-- the verdict kind that was tried, the check it was tried against, and the epoch the
-- completion carried. It defaults to NULL, so the three-argument call remains legal and
-- the diagnosis degrades to the parts the rows can still prove.
--
-- NO VOLATILITY MARKER, and that is a MEASUREMENT rather than an omission. `STABLE` is
-- what this function deserves — it reads tables and reads now() to decide whether a
-- disposition has expired, and it writes nothing — but CockroachDB v26.2.5 refuses to
-- create it: `22023: volatile statement not allowed in stable function: DECLARE`. A
-- PL/pgSQL body with a DECLARE block cannot be marked STABLE on this version, so the
-- default (VOLATILE) stands. The read-only property is not enforced by the marker; it is
-- enforced by there being no write statement in the body, and by the conformance suite
-- asserting that a diagnosis leaves the database byte-identical.
--
-- CREATE FUNCTION, deliberately not CREATE OR REPLACE. Two bindings applied to one
-- database would both claim this name; OR REPLACE would let the second silently overwrite
-- the first vertical's diagnoser, and a silently overwritten diagnoser is worse than a
-- migration that refuses with 42723 and names the collision.

CREATE FUNCTION trappoint.explain_refusal(
  p_subject_kind STRING,
  p_subject_id   UUID,
  p_constraint   STRING,
  p_attempt      JSONB DEFAULT NULL
) RETURNS JSONB
  LANGUAGE plpgsql
  AS $fn$
DECLARE
  v_epoch        INT8   := NULL;
  v_state        STRING := NULL;
  v_value        INT8   := NULL;
  v_open_n       INT8   := 0;
  v_atoms        JSONB  := NULL;
  v_ids          JSONB  := NULL;
  v_mus          JSONB  := NULL;
  v_naa          JSONB  := NULL;
  v_reason       STRING := NULL;
  v_diagnosis    STRING := 'declarative';
  v_kinds        STRING[] := NULL;
  v_vir          STRING := NULL;
  v_attempt_kind STRING := NULL;
  v_attempt_chk  UUID   := NULL;
  v_attempt_ep   INT8   := NULL;
  v_handled      BOOL   := false;
BEGIN
  IF p_constraint IS NULL OR p_constraint = '' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT: a refusal with no exhibit is not evidence';
  END IF;
  IF p_subject_id IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT: a refusal with no subject cannot be diagnosed';
  END IF;
  IF p_attempt IS NOT NULL THEN
    v_attempt_kind := p_attempt->>'kind';
    v_attempt_chk  := (p_attempt->>'check_id')::UUID;
    v_attempt_ep   := (p_attempt->>'gate_epoch')::INT8;
  END IF;

  -- ── the subject, read once ──────────────────────────────────────────────────────
  -- The epoch is not decoration: a refusal payload without it cannot be replayed, because
  -- the obligation set it names is only the obligation set AT THAT EPOCH.
  IF p_subject_kind = 'permit' THEN
    SELECT sub.gate_epoch, sub.state::STRING
      INTO v_epoch, v_state
      FROM mainline.permit AS sub
     WHERE sub.permit_id = p_subject_id;
  END IF;
  IF p_subject_kind = 'change_request' THEN
    SELECT sub.gate_epoch, sub.state::STRING
      INTO v_epoch, v_state
      FROM mainline.change_request AS sub
     WHERE sub.cr_id = p_subject_id;
  END IF;
  IF v_epoch IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT: no such subject — a refusal cannot be diagnosed against a row that does not exist';
  END IF;

  -- ── 1. THE COUNTER REFUSALS ─────────────────────────────────────────────────────
  -- One branch per (subject, counter) the binding declares. The constraint names below
  -- are the binding's, not this template's: `trappoint render` writes what
  -- `vertical.toml` says, and a vertical that renames a constraint gets a decomposition
  -- that renames with it.

  IF NOT v_handled AND p_subject_kind = 'permit'
     AND p_constraint = 'gate_closed_when_issued' THEN
    v_handled := true;
    SELECT sub.open_blocking INTO v_value
      FROM mainline.permit AS sub
     WHERE sub.permit_id = p_subject_id;
    IF v_value IS NULL OR v_value <= 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the current row';
    END IF;
    -- The flagship. `blocking_check` is a substrate table this kernel renders, so
    -- the decomposition can name its rows: the open obligations ARE the reason set.
    --
    -- `legal` is the INTERSECTION of the verdict kinds legal at every classification
    -- present in the open set — a kind outside the intersection would not clear one of
    -- them, and an alternative that does not restore admissibility is not an alternative.
    WITH open_obl AS (
      SELECT bc.check_id,
             bc.origin,
             bc.clause_uuid,
             bc.precursor_event_id,
             bc.severity,
             bc.virulence
        FROM mainline.blocking_check AS bc
       WHERE bc.permit_id = p_subject_id
         AND NOT EXISTS (
               SELECT 1
                 FROM mainline.disposition AS d
                WHERE d.check_id = bc.check_id
                  AND d.retracted_by IS NULL
                  AND (d.expires_at IS NULL OR d.expires_at > now()))
    ), vir AS (
      SELECT DISTINCT o.virulence FROM open_obl AS o
    ), legal AS (
      SELECT cl.kind
        FROM mainline.clearance_legal AS cl
       WHERE cl.virulence IN (SELECT v.virulence FROM vir AS v)
       GROUP BY cl.kind
      HAVING count(DISTINCT cl.virulence) = (SELECT count(*) FROM vir)
    )
    SELECT coalesce((SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                              'kind', 'obligation',
                              'obligation_id', o.check_id,
                              'origin', o.origin,
                              'clause_id', o.clause_uuid,
                              'event_id', o.precursor_event_id,
                              'severity', o.severity,
                              'virulence', o.virulence,
                              'detail', 'open at gate_epoch ' || v_epoch::STRING
                                        || '; no live disposition'))
                            ORDER BY o.check_id)
                      FROM open_obl AS o), '[]'::JSONB),
           coalesce((SELECT jsonb_agg(o.check_id ORDER BY o.check_id) FROM open_obl AS o),
                    '[]'::JSONB),
           (SELECT count(*) FROM open_obl),
           (SELECT array_agg(l.kind ORDER BY l.kind) FROM legal AS l)
      INTO v_atoms, v_ids, v_open_n, v_kinds;
    IF v_open_n = 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: projected counter disagrees with the re-derived witness set — refusing on drift';
    END IF;
    v_mus := v_atoms;
    v_naa := jsonb_strip_nulls(jsonb_build_object(
               'kind', 'dispose_obligations',
               'cardinality', v_open_n,
               'obligation_ids', v_ids,
               'legal_kinds', to_jsonb(v_kinds),
               'description', v_open_n::STRING
                              || ' obligation(s) remain open on this subject; disposing of '
                              || 'exactly those restores admissibility'));
  END IF;

  IF NOT v_handled AND p_subject_kind = 'permit'
     AND p_constraint = 'identity_conserved_when_issued' THEN
    v_handled := true;
    SELECT sub.open_residue INTO v_value
      FROM mainline.permit AS sub
     WHERE sub.permit_id = p_subject_id;
    IF v_value IS NULL OR v_value <= 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the current row';
    END IF;
    -- A counter fed by a relation the VERTICAL declares. The substrate will not invent
    -- witness rows for a table it does not own, so the atom names the counter, its
    -- required value and its observed value — every one of which is a fact — and stops.
    v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
               'kind', 'capability_gap',
               'capability', 'mainline.permit.open_residue',
               'required_value', 0,
               'observed_value', v_value,
               'detail', 'projected counter is non-zero; its source relation is declared by '
                         || 'the vertical, so the substrate names the counter rather than '
                         || 'inventing its witness rows')));
    v_naa := jsonb_build_object(
               'kind', 'supply_evidence',
               'required', jsonb_build_array('mainline.permit.open_residue'),
               'cardinality', v_value,
               'description', v_value::STRING
                              || ' obligation(s) feed this counter; resolving exactly those '
                              || 'restores admissibility');
  END IF;

  IF NOT v_handled AND p_subject_kind = 'permit'
     AND p_constraint = 'conflicts_resolved_when_issued' THEN
    v_handled := true;
    SELECT sub.open_conflicts INTO v_value
      FROM mainline.permit AS sub
     WHERE sub.permit_id = p_subject_id;
    IF v_value IS NULL OR v_value <= 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the current row';
    END IF;
    -- A counter fed by a relation the VERTICAL declares. The substrate will not invent
    -- witness rows for a table it does not own, so the atom names the counter, its
    -- required value and its observed value — every one of which is a fact — and stops.
    v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
               'kind', 'capability_gap',
               'capability', 'mainline.permit.open_conflicts',
               'required_value', 0,
               'observed_value', v_value,
               'detail', 'projected counter is non-zero; its source relation is declared by '
                         || 'the vertical, so the substrate names the counter rather than '
                         || 'inventing its witness rows')));
    v_naa := jsonb_build_object(
               'kind', 'supply_evidence',
               'required', jsonb_build_array('mainline.permit.open_conflicts'),
               'cardinality', v_value,
               'description', v_value::STRING
                              || ' obligation(s) feed this counter; resolving exactly those '
                              || 'restores admissibility');
  END IF;

  IF NOT v_handled AND p_subject_kind = 'permit'
     AND p_constraint = 'no_open_warrant_when_issued' THEN
    v_handled := true;
    SELECT sub.open_warrants INTO v_value
      FROM mainline.permit AS sub
     WHERE sub.permit_id = p_subject_id;
    IF v_value IS NULL OR v_value <= 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the current row';
    END IF;
    -- A counter fed by a relation the VERTICAL declares. The substrate will not invent
    -- witness rows for a table it does not own, so the atom names the counter, its
    -- required value and its observed value — every one of which is a fact — and stops.
    v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
               'kind', 'capability_gap',
               'capability', 'mainline.permit.open_warrants',
               'required_value', 0,
               'observed_value', v_value,
               'detail', 'projected counter is non-zero; its source relation is declared by '
                         || 'the vertical, so the substrate names the counter rather than '
                         || 'inventing its witness rows')));
    v_naa := jsonb_build_object(
               'kind', 'supply_evidence',
               'required', jsonb_build_array('mainline.permit.open_warrants'),
               'cardinality', v_value,
               'description', v_value::STRING
                              || ' obligation(s) feed this counter; resolving exactly those '
                              || 'restores admissibility');
  END IF;

  IF NOT v_handled AND p_subject_kind = 'permit'
     AND p_constraint = 'boundary_certified_when_issued' THEN
    v_handled := true;
    SELECT sub.unmodelled_asset_count INTO v_value
      FROM mainline.permit AS sub
     WHERE sub.permit_id = p_subject_id;
    IF v_value IS NULL OR v_value <= 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the current row';
    END IF;
    -- A counter fed by a relation the VERTICAL declares. The substrate will not invent
    -- witness rows for a table it does not own, so the atom names the counter, its
    -- required value and its observed value — every one of which is a fact — and stops.
    v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
               'kind', 'capability_gap',
               'capability', 'mainline.permit.unmodelled_asset_count',
               'required_value', 0,
               'observed_value', v_value,
               'detail', 'projected counter is non-zero; its source relation is declared by '
                         || 'the vertical, so the substrate names the counter rather than '
                         || 'inventing its witness rows')));
    v_naa := jsonb_build_object(
               'kind', 'supply_evidence',
               'required', jsonb_build_array('mainline.permit.unmodelled_asset_count'),
               'cardinality', v_value,
               'description', v_value::STRING
                              || ' obligation(s) feed this counter; resolving exactly those '
                              || 'restores admissibility');
  END IF;

  IF NOT v_handled AND p_subject_kind = 'permit'
     AND p_constraint = 'reading_floor_when_issued' THEN
    v_handled := true;
    SELECT sub.unmet_floor_count INTO v_value
      FROM mainline.permit AS sub
     WHERE sub.permit_id = p_subject_id;
    IF v_value IS NULL OR v_value <= 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the current row';
    END IF;
    -- A counter fed by a relation the VERTICAL declares. The substrate will not invent
    -- witness rows for a table it does not own, so the atom names the counter, its
    -- required value and its observed value — every one of which is a fact — and stops.
    v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
               'kind', 'capability_gap',
               'capability', 'mainline.permit.unmet_floor_count',
               'required_value', 0,
               'observed_value', v_value,
               'detail', 'projected counter is non-zero; its source relation is declared by '
                         || 'the vertical, so the substrate names the counter rather than '
                         || 'inventing its witness rows')));
    -- `offset_allowed`: the constraint is satisfied either by the counter reaching zero or
    -- by its companion offset being present. Naming the companion column exactly needs
    -- `offset_column`, which the binding declares and the render context does not yet
    -- carry; until it does, the alternative names the constraint whose offset it is.
    v_naa := jsonb_build_object(
               'kind', 'supply_evidence',
               'required', jsonb_build_array('reading_floor_when_issued'),
               'cardinality', 1,
               'description', 'this constraint admits an offsetting companion counter; '
                              || 'supplying one satisfies it without the counter reaching zero');
  END IF;

  IF NOT v_handled AND p_subject_kind = 'change_request'
     AND p_constraint = 'cr_gate_closed_when_merged' THEN
    v_handled := true;
    SELECT sub.open_blocking INTO v_value
      FROM mainline.change_request AS sub
     WHERE sub.cr_id = p_subject_id;
    IF v_value IS NULL OR v_value <= 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the current row';
    END IF;
    -- The flagship. `blocking_check` is a substrate table this kernel renders, so
    -- the decomposition can name its rows: the open obligations ARE the reason set.
    --
    -- `legal` is the INTERSECTION of the verdict kinds legal at every classification
    -- present in the open set — a kind outside the intersection would not clear one of
    -- them, and an alternative that does not restore admissibility is not an alternative.
    WITH open_obl AS (
      SELECT bc.check_id,
             bc.origin,
             bc.clause_uuid,
             bc.precursor_event_id,
             bc.severity,
             bc.virulence
        FROM mainline.blocking_check AS bc
       WHERE bc.cr_id = p_subject_id
         AND NOT EXISTS (
               SELECT 1
                 FROM mainline.disposition AS d
                WHERE d.check_id = bc.check_id
                  AND d.retracted_by IS NULL
                  AND (d.expires_at IS NULL OR d.expires_at > now()))
    ), vir AS (
      SELECT DISTINCT o.virulence FROM open_obl AS o
    ), legal AS (
      SELECT cl.kind
        FROM mainline.clearance_legal AS cl
       WHERE cl.virulence IN (SELECT v.virulence FROM vir AS v)
       GROUP BY cl.kind
      HAVING count(DISTINCT cl.virulence) = (SELECT count(*) FROM vir)
    )
    SELECT coalesce((SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                              'kind', 'obligation',
                              'obligation_id', o.check_id,
                              'origin', o.origin,
                              'clause_id', o.clause_uuid,
                              'event_id', o.precursor_event_id,
                              'severity', o.severity,
                              'virulence', o.virulence,
                              'detail', 'open at gate_epoch ' || v_epoch::STRING
                                        || '; no live disposition'))
                            ORDER BY o.check_id)
                      FROM open_obl AS o), '[]'::JSONB),
           coalesce((SELECT jsonb_agg(o.check_id ORDER BY o.check_id) FROM open_obl AS o),
                    '[]'::JSONB),
           (SELECT count(*) FROM open_obl),
           (SELECT array_agg(l.kind ORDER BY l.kind) FROM legal AS l)
      INTO v_atoms, v_ids, v_open_n, v_kinds;
    IF v_open_n = 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: projected counter disagrees with the re-derived witness set — refusing on drift';
    END IF;
    v_mus := v_atoms;
    v_naa := jsonb_strip_nulls(jsonb_build_object(
               'kind', 'dispose_obligations',
               'cardinality', v_open_n,
               'obligation_ids', v_ids,
               'legal_kinds', to_jsonb(v_kinds),
               'description', v_open_n::STRING
                              || ' obligation(s) remain open on this subject; disposing of '
                              || 'exactly those restores admissibility'));
  END IF;

  IF NOT v_handled AND p_subject_kind = 'change_request'
     AND p_constraint = 'cr_identity_conserved_when_merged' THEN
    v_handled := true;
    SELECT sub.open_residue INTO v_value
      FROM mainline.change_request AS sub
     WHERE sub.cr_id = p_subject_id;
    IF v_value IS NULL OR v_value <= 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the current row';
    END IF;
    -- A counter fed by a relation the VERTICAL declares. The substrate will not invent
    -- witness rows for a table it does not own, so the atom names the counter, its
    -- required value and its observed value — every one of which is a fact — and stops.
    v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
               'kind', 'capability_gap',
               'capability', 'mainline.change_request.open_residue',
               'required_value', 0,
               'observed_value', v_value,
               'detail', 'projected counter is non-zero; its source relation is declared by '
                         || 'the vertical, so the substrate names the counter rather than '
                         || 'inventing its witness rows')));
    v_naa := jsonb_build_object(
               'kind', 'supply_evidence',
               'required', jsonb_build_array('mainline.change_request.open_residue'),
               'cardinality', v_value,
               'description', v_value::STRING
                              || ' obligation(s) feed this counter; resolving exactly those '
                              || 'restores admissibility');
  END IF;

  IF NOT v_handled AND p_subject_kind = 'change_request'
     AND p_constraint = 'cr_conflicts_resolved_when_merged' THEN
    v_handled := true;
    SELECT sub.open_conflicts INTO v_value
      FROM mainline.change_request AS sub
     WHERE sub.cr_id = p_subject_id;
    IF v_value IS NULL OR v_value <= 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the current row';
    END IF;
    -- A counter fed by a relation the VERTICAL declares. The substrate will not invent
    -- witness rows for a table it does not own, so the atom names the counter, its
    -- required value and its observed value — every one of which is a fact — and stops.
    v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
               'kind', 'capability_gap',
               'capability', 'mainline.change_request.open_conflicts',
               'required_value', 0,
               'observed_value', v_value,
               'detail', 'projected counter is non-zero; its source relation is declared by '
                         || 'the vertical, so the substrate names the counter rather than '
                         || 'inventing its witness rows')));
    v_naa := jsonb_build_object(
               'kind', 'supply_evidence',
               'required', jsonb_build_array('mainline.change_request.open_conflicts'),
               'cardinality', v_value,
               'description', v_value::STRING
                              || ' obligation(s) feed this counter; resolving exactly those '
                              || 'restores admissibility');
  END IF;

  -- ── 2. THE CLEARANCE LATTICE ────────────────────────────────────────────────────
  -- 23503 on the composite foreign key into the typed clearance table. The classification
  -- is a PROJECTION: it comes from the subject's open obligations, never from the row that
  -- was refused — which is exactly why the refusal could not be argued with.
  --
  -- The alternative is the set of kinds that DO exist at that classification. Where that
  -- set is empty, `naa` is null with `no_legal_verdict_exists`, and that is not a failure
  -- of the diagnoser: it is the sentence the product exists to be able to say.
  IF NOT v_handled AND p_constraint = 'fk_clearance' THEN
    v_handled := true;
    WITH open_obl AS (
      SELECT bc.check_id,
             bc.origin,
             bc.clause_uuid,
             bc.precursor_event_id,
             bc.severity,
             bc.virulence
        FROM mainline.blocking_check AS bc
       WHERE (bc.permit_id = p_subject_id OR bc.cr_id = p_subject_id)
         AND (v_attempt_chk IS NULL OR bc.check_id = v_attempt_chk)
         AND NOT EXISTS (
               SELECT 1
                 FROM mainline.disposition AS d
                WHERE d.check_id = bc.check_id
                  AND d.retracted_by IS NULL
                  AND (d.expires_at IS NULL OR d.expires_at > now()))
    ), vir AS (
      SELECT DISTINCT o.virulence FROM open_obl AS o
    ), legal AS (
      SELECT cl.kind
        FROM mainline.clearance_legal AS cl
       WHERE cl.virulence IN (SELECT v.virulence FROM vir AS v)
       GROUP BY cl.kind
      HAVING count(DISTINCT cl.virulence) = (SELECT count(*) FROM vir)
    )
    SELECT coalesce((SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                              'kind', 'obligation',
                              'obligation_id', o.check_id,
                              'origin', o.origin,
                              'clause_id', o.clause_uuid,
                              'event_id', o.precursor_event_id,
                              'severity', o.severity,
                              'virulence', o.virulence,
                              'detail', 'classification projected from the authority source, '
                                        || 'not from the inserted row'))
                            ORDER BY o.check_id)
                      FROM open_obl AS o), '[]'::JSONB),
           (SELECT count(*) FROM open_obl),
           (SELECT array_to_string(array_agg(v.virulence::STRING ORDER BY v.virulence::STRING),
                                   ', ')
              FROM vir AS v),
           (SELECT array_agg(l.kind ORDER BY l.kind) FROM legal AS l)
      INTO v_atoms, v_open_n, v_vir, v_kinds;

    IF v_open_n = 0 THEN
      -- No open obligation carries a classification, so there is nothing to project one
      -- from. Saying so is the honest answer; guessing a virulence would be the dishonest
      -- one, and it is the guess that would end up in a courtroom.
      v_diagnosis := 'none';
      v_reason := 'not_computable';
      v_mus := jsonb_build_array(jsonb_build_object(
                 'kind', 'capability_gap',
                 'capability', 'mainline.clearance_legal',
                 'detail', 'no open obligation on this subject carries a classification, so '
                           || 'the refused verdict cannot be placed in the lattice'));
      v_naa := NULL;
    ELSE
      v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
                 'kind', 'capability_gap',
                 'capability', 'mainline.clearance_legal.'
                               || coalesce(v_attempt_kind, 'verdict'),
                 'required_value', v_vir,
                 'observed_value', NULL,
                 'detail', 'no row (' || coalesce(v_vir, 'unknown') || ', '
                           || coalesce(v_attempt_kind, 'the attempted kind')
                           || ') exists in the typed clearance table'))) || v_atoms;
      IF v_kinds IS NULL OR array_length(v_kinds, 1) IS NULL THEN
        v_naa := NULL;
        v_reason := 'no_legal_verdict_exists';
      ELSE
        v_naa := jsonb_build_object(
                   'kind', 'substitute_kind',
                   'legal_kinds', to_jsonb(v_kinds),
                   'cardinality', 1,
                   'description', array_length(v_kinds, 1)::STRING
                                  || ' clearance kind(s) exist at this classification; the '
                                  || 'attempted verdict is not one of them');
      END IF;
    END IF;
  END IF;

  -- ── 3. THE EPOCH PIN ────────────────────────────────────────────────────────────
  -- 23503 on the completion record's composite foreign key. Matched on the `epoch_pin_`
  -- prefix rather than on an exact name because the pin constraint is named per subject
  -- kind and the render context carries the subjects, not their pin names.
  --
  -- Two shapes, and the difference matters to the person reading it. If the subject has
  -- already reached its completing state, the pin is doing what it exists to do and the
  -- only admissible path is a CHILD subject — git discipline expressed as referential
  -- integrity. If it has not, the epoch simply moved under the attempt: an obligation
  -- arrived, the counter bumped it, and the completion was prepared against a stale value.
  IF NOT v_handled AND left(p_constraint, 10) = 'epoch_pin_' THEN
    v_handled := true;
    IF v_state IN ('merged') THEN
      v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
                 'kind', 'capability_gap',
                 'capability', p_subject_kind || '.gate_epoch',
                 'required_value', v_epoch,
                 'observed_value', v_attempt_ep,
                 'detail', 'the completed transition pins this subject at its epoch, and '
                           || 'ON UPDATE RESTRICT refuses any change to it')));
      v_naa := jsonb_build_object(
                 'kind', 'fork_subject',
                 'parent_subject_id', p_subject_id,
                 'cardinality', 1,
                 'description', 'the subject is completed and pinned; the only admissible '
                                || 'path is a child subject whose gate is cleared afresh');
    ELSE
      v_mus := jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
                 'kind', 'capability_gap',
                 'capability', p_subject_kind || '.gate_epoch',
                 'required_value', v_epoch,
                 'observed_value', v_attempt_ep,
                 'detail', 'the epoch moved after the completion was prepared; a new '
                           || 'obligation bumped it')));
      v_naa := jsonb_build_object(
                 'kind', 'supply_evidence',
                 'required', jsonb_build_array('gate_epoch'),
                 'cardinality', 1,
                 'description', 'read the subject epoch again and re-attempt the completion '
                                || 'against it, having disposed of what bumped it');
    END IF;
  END IF;

  -- ── 4. EVERYTHING ELSE ──────────────────────────────────────────────────────────
  -- Honest incompleteness. `diagnosis = "none"` says the set is a candidate and not a
  -- proven minimal one, and a consumer must not present it as irreducible. Shipping a
  -- superset labelled `declarative` would be the one failure this invariant exists to
  -- prevent.
  IF NOT v_handled THEN
    v_diagnosis := 'none';
    v_reason := 'not_computable';
    v_naa := NULL;
    v_mus := jsonb_build_array(jsonb_build_object(
               'kind', 'capability_gap',
               'capability', left(p_constraint, 128),
               'detail', 'outside the declarative decomposition; the general algorithm is '
                         || 'QuickXplain over savepoint probes, in a separate transaction '
                         || 'and never on the completion path'));
  END IF;

  RETURN jsonb_build_object(
    'spec_version', '1.0.0-rc.1',
    'profile', 'mainline',
    'class', 'gate',
    'constraint', p_constraint,
    'subject_kind', p_subject_kind,
    'subject_id', p_subject_id,
    'gate_epoch', v_epoch,
    'diagnosis', v_diagnosis,
    'probe_calls', 0,
    'mus', v_mus,
    'naa', v_naa,
    'naa_reason', v_reason);
END
$fn$;
