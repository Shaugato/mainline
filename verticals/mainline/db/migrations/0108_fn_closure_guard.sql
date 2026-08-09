-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0108_fn_closure_guard.sql
-- CREATE FUNCTION mainline.fn_closure_guard — generations dense, severity monotone, every write ledgered
--
-- MI: MI26, MI15, MI01
-- I: I05
-- COUNSEL-GATED: no
-- RATIONALE: Finding S2: every ancestry gate reads the blame closure, and the closure was
--            mutable, un-granted, un-ledgered and un-guarded, so a single UPDATE was a
--            shorter path to a laundered gate than any attack the design was defending
--            against. Generations must be dense so a rewrite cannot hide between two
--            numbers nobody audits; severity may fall only against a signed second-rater
--            revision written in the same transaction; and every write leaves a custody
--            intake row in that transaction, so a closure rewrite is impossible to perform
--            invisibly. The trigger does not compute the evidentiary hash — SQL cannot —
--            and does not pretend to.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0107_fn_closure_guard.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- migration:  0108_fn_closure_guard
-- band:       0100-0109z · kernel/projection-triggers · RENDERED
-- statements: 1
-- invariants: MI26 — the blame closure is append-only, generation-dense and severity-monotone
--             across generations. This function is the DENSE and MONOTONE halves; the
--             append-only half is `fn_refuse_mutation` welded by the 0128 family, and the grant
--             half is `agent_projector` holding INSERT on this table and nothing else.
-- source:     ARCHITECTURE.md §5.11 item 6 · §2.2 S2 · docs/leads/custody.md A10
-- requires:   mainline.clause_blame_closure · mainline.site (site_code) ·
--             mainline.ledger_intake · mainline.event_severity_revision
-- provides:   mainline.fn_closure_guard() — welded to clause_blame_closure by 0127
-- sqlstate:   P0001 on a non-dense generation, on a silent severity downgrade, and on a closure
--             whose site has no row. 23514 from ledger_intake's own CHECKs if the placeholder
--             bytes were ever narrowed. 23503 on fk_site is unreachable BECAUSE site_code is
--             projected here rather than cast.
-- grants:     agent_projector needs INSERT on clause_blame_closure and on ledger_intake, and
--             SELECT on site — nothing more, and nothing on any gated subject. Grants are cluster
--             state applied by the declarative matrix, never by a migration; this line is the
--             statement of what the matrix must say, and the privilege probe is the evidence.
-- forward-only; no .down.sql and no .up.sql (MR-5).
--
-- ACYCLICITY. BEFORE INSERT on clause_blame_closure; reads that table, `site` and
-- `event_severity_revision`, and writes `ledger_intake`, whose only trigger is the append-only
-- guard on UPDATE and DELETE. Trigger depth contributed: 1.

CREATE FUNCTION mainline.fn_closure_guard() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_prev_severity INT2;
  v_prev_gen INT8;
  v_revisions INT8;
  v_site_code STRING;
BEGIN
  -- The immediately preceding generation for this exact clause version, by primary-key prefix.
  SELECT c.max_severity, c.closure_gen
    INTO v_prev_severity, v_prev_gen
    FROM mainline.clause_blame_closure c
   WHERE c.clause_uuid = (NEW).clause_uuid
     AND c.as_of_commit = (NEW).as_of_commit
   ORDER BY c.closure_gen DESC
   LIMIT 1;

  -- DENSE: the first generation is zero and every later one is exactly one more. A closure that
  -- may start at any number is a closure with room to hide a rewrite in.
  IF v_prev_gen IS NULL AND (NEW).closure_gen <> 0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: the first closure generation for a clause version must be zero';
  END IF;
  IF v_prev_gen IS NOT NULL AND (NEW).closure_gen <> v_prev_gen + 1 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: closure generations must be dense and monotone';
  END IF;

  -- MONOTONE: upgrades are free, downgrades cost a signed second-rater revision IN THIS
  -- TRANSACTION. The one aggregate this body is allowed (§4.1 law 4), and it is nested inside
  -- the only branch that needs it.
  IF v_prev_severity IS NOT NULL AND (NEW).max_severity < v_prev_severity THEN
    SELECT count(*) INTO v_revisions
      FROM mainline.event_severity_revision r
     WHERE r.at >= transaction_timestamp();
    IF v_revisions = 0 THEN
      RAISE EXCEPTION USING ERRCODE='P0001',
        MESSAGE='MAINLINE: closure severity may not decrease without a signed severity revision';
    END IF;
  END IF;

  -- The ledger partition key HAS A SOURCE. Projected, never cast from site_id, and absence
  -- refuses.
  SELECT st.site_code INTO v_site_code
    FROM mainline.site st
   WHERE st.site_id = (NEW).site_id;
  IF v_site_code IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no site row for this closure — the ledger partition key has no source';
  END IF;

  -- LEDGERED IN THE SAME TRANSACTION. canon_bytes and leaf_hash are SENTINEL PLACEHOLDERS: one
  -- zero byte and thirty-two zero bytes. They satisfy ledger_intake's own CHECKs, they are not
  -- valid RFC 8785 bytes, and the relay recomputes both client-side before sequencing.
  INSERT INTO mainline.ledger_intake
              (site_code, entry_kind, subject_id, actor, actor_kind, payload,
               canon_bytes, payload_ver, leaf_hash, hlc)
       VALUES (v_site_code, 'closure', (NEW).clause_uuid, (NEW).computed_by, 'service',
               jsonb_build_object(
                 'clause_uuid',    (NEW).clause_uuid,
                 'as_of_commit',   encode((NEW).as_of_commit, 'hex'),
                 'closure_gen',    (NEW).closure_gen,
                 'max_severity',   (NEW).max_severity,
                 'ancestor_count', (NEW).ancestor_count,
                 'truncated',      (NEW).truncated),
               decode('00', 'hex'), 1, decode(repeat('0', 64), 'hex'),
               cluster_logical_timestamp());
  RETURN NEW;
END $$;
