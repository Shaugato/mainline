-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0102_fn_disposition_project.sql
-- CREATE FUNCTION trappoint_ref.fn_disposition_project — identity, virulence and deliberation are projections
--
-- MI: MI11, MI27, MI28, MI29
-- I: I09, I10, I15
-- COUNSEL-GATED: no
-- RATIONALE: Findings S1 and S7 in one function. Virulence, closure generation and severity
--            are re-derived from the blame closure rather than inherited from the blocking
--            check, so a laundered check cannot launder its disposition. Rank, organisation
--            and the competency triple are projected from the live person row and frozen,
--            so a client signing with a rank it does not hold is overwritten before
--            rank_floor compares. Deliberation derives from the server-issued exposure
--            receipt. A missing clearance row projects the strictest legal values under
--            ruling D3 rather than raising a synthetic 23503, because a synthetic code
--            carries no constraint name and the constraint name is the exhibit.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0102_fn_disposition_project.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- migration:  0102_fn_disposition_project
-- band:       0100-0109z · kernel/projection-triggers · RENDERED
-- statements: 1
-- invariants: MI27 (identity, rank, org and competency are projections of person; a missing
--             person row refuses) · MI11 (no disposition kind dismisses a fatality-written
--             control — enforced by fk_clearance, ARMED by the virulence projected here) ·
--             MI29 (overrides escalate against the person across permits, no ceiling)
-- source:     ARCHITECTURE.md §5.11 item 3 · §2.2 S1, S7, S8, S19 ·
--             docs/leads/kernel.md D2, D3, D4 · spec/binding/authority-source.md §5
-- requires:   trappoint_ref.blocking_check (0058) · trappoint_ref.exposure_receipt (0061) ·
--             trappoint_ref.disposition_citation (0067) · trappoint_ref.override_ledger (0068) ·
--             trappoint_ref.clause_blame_current · trappoint_ref.clearance_legal · trappoint_ref.person ·
--             trappoint_ref_meas.recall_policy (the reading-rate policy; absent values fall back to
--             the substrate defaults tau0 = 5 s and rho = 4 tokens/s, which is a DEGRADATION,
--             not a pass — the floor still computes and still projects)
-- provides:   trappoint_ref.fn_disposition_project() — welded to disposition by 0122
-- sqlstate:   P0001 on an unknown check, an absent closure, an absent or expired exposure
--             receipt, and an unknown signer or countersigner. 23503 on fk_clearance for an
--             illegal (virulence, kind) pair — raised BY THE FOREIGN KEY, never here (D3).
-- forward-only; no .down.sql and no .up.sql (MR-5).
--
-- @projects disposition.req_compensating, disposition.req_second_signer, disposition.req_foreign_org, disposition.req_predicate, disposition.req_reassert, disposition.min_signer_rank
-- @authority trappoint_ref.clearance_legal (virulence, kind) <= NEW (virulence, kind)
-- @on_missing raise
--
-- @projects disposition.signer_rank, disposition.signer_org, disposition.competency_sha256
-- @authority trappoint_ref.person (signer_sub) <= NEW (signer_sub)
-- @on_missing raise
--
-- ACYCLICITY. BEFORE INSERT on disposition, writing only to NEW. It reads six relations and
-- writes none of them. Trigger depth contributed: 0.

CREATE FUNCTION trappoint_ref.fn_disposition_project() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_subject_kind STRING;
  v_permit_id UUID;
  v_cr_id UUID;
  v_site_id UUID;
  v_ck_clause_uuid UUID;
  v_ck_commit_id BYTES;
  v_severity INT2;
  v_virulence trappoint_ref.virulence_class;
  v_closure_gen INT8;
  v_req_compensating BOOL;
  v_req_second_signer BOOL;
  v_req_foreign_org BOOL;
  v_req_predicate BOOL;
  v_req_reassert BOOL;
  v_min_signer_rank INT2;
  v_max_ttl_hours INT4;
  v_signer_rank INT2;
  v_signer_org STRING;
  v_competency_sha256 BYTES;
  v_competency_source_id UUID;
  v_competency_snapshot JSONB;
  v_co_rank INT2;
  v_co_org STRING;
  v_issued_at TIMESTAMPTZ;
  v_expires_at TIMESTAMPTZ;
  v_tokens INT8;
  v_tau0 FLOAT8;
  v_rho FLOAT8;
  v_anchors INT4;
  v_overrides INT8;
  v_deliberation INT8;
BEGIN
  -- 1 · WHICH OBLIGATION IS THIS. The subject, the site and the clause version all come from the
  -- check row, never from the inserter: a disposition that names its own permit is a disposition
  -- that can be filed against a permit its check never blocked.
  SELECT bc.subject_kind, bc.permit_id, bc.cr_id, bc.site_id, bc.clause_uuid, bc.commit_id
    INTO v_subject_kind, v_permit_id, v_cr_id, v_site_id, v_ck_clause_uuid, v_ck_commit_id
    FROM trappoint_ref.blocking_check bc
   WHERE bc.check_id = (NEW).check_id;
  IF v_subject_kind IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='TRAPPOINT_REF: no such blocking check — a disposition cannot be filed against an obligation that does not exist';
  END IF;

  -- 2 · FINDING S1. Virulence comes from the CLOSURE at this transaction's timestamp, reached
  -- through the check's clause version. It is never inherited from the check row, so a laundered
  -- check cannot launder the disposition even if 0100 were disabled.
  SELECT c.max_severity, c.virulence, c.closure_gen
    INTO v_severity, v_virulence, v_closure_gen
    FROM trappoint_ref.clause_blame_current c
   WHERE c.clause_uuid = v_ck_clause_uuid AND c.as_of_commit = v_ck_commit_id;
  IF v_severity IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='TRAPPOINT_REF: blame closure absent — a disposition cannot be typed';
  END IF;

  -- 3 · WHAT WAS ACTUALLY SHOWN, AND WHEN THE SERVER SHOWED IT. `issued_at` is a server DEFAULT
  -- now() on a row the kernel wrote. Expiry is a trigger comparison and never a CHECK, because
  -- now() is not immutable and a CHECK sees only the row being written (§4.1 law 1).
  SELECT er.issued_at, er.expires_at, er.total_tokens
    INTO v_issued_at, v_expires_at, v_tokens
    FROM trappoint_ref.exposure_receipt er
   WHERE er.receipt_id = (NEW).receipt_id;
  IF v_expires_at IS NULL OR v_expires_at <= now() THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='TRAPPOINT_REF: exposure receipt absent or expired — re-materialise before signing';
  END IF;

  -- 4 · THE CLEARANCE LATTICE, keyed on the virulence THIS FUNCTION derived and the kind the
  -- signer chose. Ruling D3: a miss projects the strictest values and returns; fk_clearance then
  -- refuses with 23503 and its own name.
  -- The first key column is `virulence`, and it is READ FROM v_virulence RATHER THAN FROM
  -- NEW. That substitution IS finding S1: reading (NEW).virulence here would let the signer
  -- choose which row of the clearance lattice judges the signature.
  SELECT cl.req_compensating, cl.req_second_signer, cl.req_foreign_org, cl.req_predicate, cl.req_reassert, cl.min_signer_rank, cl.max_ttl_hours
    INTO v_req_compensating, v_req_second_signer, v_req_foreign_org, v_req_predicate, v_req_reassert, v_min_signer_rank, v_max_ttl_hours
    FROM trappoint_ref.clearance_legal cl
   WHERE cl.virulence = v_virulence
     AND cl.kind = (NEW).kind;
  IF v_req_compensating IS NULL THEN
    v_req_compensating := true;
    v_req_second_signer := true;
    v_req_foreign_org := true;
    v_req_predicate := true;
    v_req_reassert := true;
    v_min_signer_rank := 9;
    v_max_ttl_hours := NULL;
  END IF;

  -- 5 · FINDING S7. Identity and competency are projected from the live person row and frozen
  -- here. The current row for a signer is the FIRST row of the primary-key scan, because
  -- `person` is keyed (signer_sub, effective_from DESC).
  SELECT pr.rank, pr.org, pr.competency_sha256, pr.competency_source_id, pr.competency_snapshot
    INTO v_signer_rank, v_signer_org, v_competency_sha256, v_competency_source_id, v_competency_snapshot
    FROM trappoint_ref.person pr
   WHERE pr.signer_sub = (NEW).signer_sub
     AND pr.effective_from <= now()
   ORDER BY pr.effective_from DESC
   LIMIT 1;
  IF v_signer_rank IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='TRAPPOINT_REF: no competency record for this signer — fail closed';
  END IF;

  -- 6 · THE COUNTERSIGNER IS A SIGNER. `needs_foreign_org` compares two organisation strings; if
  -- one of them is supplied by the party the requirement constrains, the requirement is a
  -- formality. Projected from the same relation, or NULL when there is no countersigner.
  IF (NEW).countersigner_sub IS NULL THEN
    v_co_rank := NULL;
    v_co_org := NULL;
  ELSE
    SELECT pr.rank, pr.org
      INTO v_co_rank, v_co_org
      FROM trappoint_ref.person pr
     WHERE pr.signer_sub = (NEW).countersigner_sub
       AND pr.effective_from <= now()
     ORDER BY pr.effective_from DESC
     LIMIT 1;
    IF v_co_rank IS NULL THEN
      RAISE EXCEPTION USING ERRCODE='P0001',
        MESSAGE='TRAPPOINT_REF: no competency record for this countersigner — fail closed';
    END IF;
  END IF;

  -- 7 · THE ONE AGGREGATE STATEMENT (§4.1 law 4). Verbatim anchors bound what may ACQUIT; the
  -- override count is the ladder that escalates against the person across permits (S8).
  SELECT (SELECT count(*)
            FROM trappoint_ref.disposition_citation dc
           WHERE dc.disposition_id = (NEW).disposition_id
             AND dc.kind = 'verbatim')::INT4,
         (SELECT count(*)
            FROM trappoint_ref.override_ledger ol
           WHERE ol.site_id = v_site_id
             AND ol.signer_sub = (NEW).signer_sub)::INT8
    INTO v_anchors, v_overrides;

  -- 8 · The reading-rate policy. Absent values degrade to the substrate defaults rather than
  -- refusing, because the floor is a MEASUREMENT that prices a countersignature, not a gate.
  SELECT (rp.tau->>'tau0')::FLOAT8, (rp.tau->>'rho')::FLOAT8
    INTO v_tau0, v_rho
    FROM trappoint_ref_meas.recall_policy rp
    JOIN trappoint_ref.exposure_receipt er2 ON er2.policy_version = rp.policy_version
   WHERE er2.receipt_id = (NEW).receipt_id;

  -- 9 · THE PROJECTION. Unconditional, every one of them.
  NEW.subject_kind := v_subject_kind;
  NEW.permit_id := v_permit_id;
  NEW.cr_id := v_cr_id;
  NEW.site_id := v_site_id;
  NEW.virulence := v_virulence;
  NEW.closure_gen := v_closure_gen;
  NEW.severity_snapshot := v_severity;
  NEW.req_compensating := v_req_compensating;
  NEW.req_second_signer := v_req_second_signer;
  NEW.req_foreign_org := v_req_foreign_org;
  NEW.req_predicate := v_req_predicate;
  NEW.req_reassert := v_req_reassert;
  NEW.min_signer_rank := v_min_signer_rank;
  NEW.max_ttl_hours := v_max_ttl_hours;
  NEW.signer_rank := v_signer_rank;
  NEW.signer_org := v_signer_org;
  NEW.competency_sha256 := v_competency_sha256;
  NEW.competency_source_id := v_competency_source_id;
  NEW.competency_snapshot := v_competency_snapshot;
  NEW.countersigner_rank := v_co_rank;
  NEW.countersigner_org := v_co_org;
  NEW.verbatim_anchor_count := v_anchors;
  NEW.prior_override_count := v_overrides;

  -- 10 · DELIBERATION AND THE READING-RATE FLOOR (S19). t_min = tau0 + tokens / rho, with rho
  -- deliberately generous at 4 tokens/s (about 240 words per minute). Positive polarity: the
  -- column records that the floor WAS met, so a row that never reached this function reads as
  -- unmet rather than as compliant.
  v_deliberation := extract(epoch FROM (now() - v_issued_at))::INT8;
  NEW.deliberation_seconds := v_deliberation;
  NEW.reading_floor_met :=
    (v_deliberation::FLOAT8 >= coalesce(v_tau0, 5::FLOAT8)
                             + (v_tokens::FLOAT8 / coalesce(v_rho, 4::FLOAT8)));
  RETURN NEW;
END $$;
