-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0112_fn_recall_policy_anchored
-- domain:     recall
-- statements: 1
-- invariants: MI18 — a recall runs only under an anchored, cosigned policy version.
-- source:     ARCHITECTURE.md §5.11 (S24: "this replaces the CHECK (true) placeholder") · §5.7
-- requires:   0080 recall_policy · 0081 recall_run · 0072-0079 ledger_checkpoint, cosignature
-- sqlstate:   P0001
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- THE ATTACK THIS REFUSES. τ is the number that decides which precursors a supervisor is shown
-- and which ones become silence-ledger rows. If a policy row can be authored — or edited, or
-- back-dated — after a run, then every silence in that run is retro-justified by a threshold
-- chosen with knowledge of the outcome. That is not a hypothetical failure mode; it is the
-- cheapest available attack on the whole evidentiary claim, it requires no code change, and it
-- would leave a database that looks entirely consistent.
--
-- So the policy's commitment must have LEFT THE TRUST BOUNDARY before any run may cite it:
-- `anchored_tree_size` must be non-NULL and must sit inside a cosigned, admissible checkpoint.
-- Retro-fitting then requires forging a checkpoint that witnesses in adverse trust domains have
-- already signed — which is the difference between a hash chain (a checksum in a database the
-- adversary owns) and evidence.
--
-- REFUSAL DEPTH, honestly. This weld is depth 1: it is a trigger, not a CHECK, because the
-- condition is a JOIN across three tables and no CHECK expression may contain a subquery. The
-- deterministic RAISE is the observable refusal and the unwelding suite says so rather than
-- claiming a redundancy that is not there. What IS structural is the FK on
-- `recall_run.policy_version`: dropping this trigger still leaves a run unable to cite a policy
-- that does not exist (23503) — it merely leaves it able to cite one that is not yet anchored.
--
-- Style (§5.11): PL/pgSQL, row-level, no FOR..IN, no FOREACH, no EXECUTE, no PERFORM, no CASE;
-- IF/ELSIF plus one scalar lookup and exactly one aggregate SELECT..INTO.

CREATE FUNCTION mainline.fn_recall_policy_anchored() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  anchored_size INT8;
  n_cosigned    INT8;
BEGIN
  SELECT rp.anchored_tree_size INTO anchored_size
    FROM mainline_meas.recall_policy rp
   WHERE rp.policy_version = NEW.policy_version;

  IF anchored_size IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: recall policy is not anchored — a run may not cite an unanchored τ';
  END IF;

  -- "Inside a cosigned checkpoint": some admissible checkpoint for this site has already
  -- committed to a tree at least as large as the policy's anchor, and a witness has signed it.
  SELECT count(*) INTO n_cosigned
    FROM mainline.ledger_checkpoint cp
    JOIN mainline.cosignature cs
      ON cs.site_code = cp.site_code AND cs.tree_size = cp.tree_size
   WHERE cp.site_code = NEW.site_id::STRING
     AND cp.tree_size >= anchored_size
     AND cp.admissible;

  IF n_cosigned = 0 THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: recall policy anchor is not inside a cosigned checkpoint';
  END IF;

  RETURN NEW;
END $$;
