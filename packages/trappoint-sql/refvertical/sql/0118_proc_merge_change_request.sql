-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0118_proc_merge_change_request.sql
-- CREATE OR REPLACE PROCEDURE trappoint_ref.merge_change_request() — the gate transaction as one server-side statement
--
-- MI: MI09, MI30
-- I: I03, I04
-- COUNSEL-GATED: no
-- RATIONALE: One round trip, and a client crash cannot leave the transition half-performed.
--            The procedure sets up the named mechanisms and gets out of their way: it
--            refuses only the two conditions nothing else can hold — a subject that does
--            not exist, and a head that moved between the anchor read and the last write —
--            because every other refusal on this path already has a constraint name
--            attached, and the constraint name is the exhibit.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0117_proc_merge.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- SUBJECT: change_request (trappoint_ref.change_request → trappoint_ref.cr_event → trappoint_ref.merge_record).
--
-- THE PARAMETERS, and why the evidentiary ones are supplied rather than computed.
-- `a_canon_bytes` is RFC 8785 JCS over `a_payload` and `a_leaf_hash` is
-- SHA-256(0x00 || canon_bytes), both produced by the CLIENT. SQL cannot canonicalise
-- to JCS — CockroachDB's own JSONB key ordering is not reproducible by a third party
-- — so a server-computed leaf would be a hash nobody outside this cluster could
-- recompute, which is the opposite of what a custody ledger is for. What the SERVER
-- computes is everything a client could lie about and a reader could check:
-- `clearance_digest`, `prev_digest`, the observed obligation count, and the sequence.
--
-- ISOLATION IS THE CALLER'S. This procedure does not and cannot set it: `SET
-- TRANSACTION ISOLATION LEVEL SERIALIZABLE` is issued by `trappoint_core.gate` on
-- every attempt, explicitly, never inherited from a pool default (spec/errors.md
-- §2.1). A procedure that silently ran at whatever the session offered would make the
-- one line of the client that matters unauditable.

CREATE OR REPLACE PROCEDURE trappoint_ref.merge_change_request(
  a_subject_id    UUID,
  a_merged_commit BYTES,
  a_merged_by     STRING,
  a_actor_kind    STRING,
  a_payload       JSONB,
  a_canon_bytes   BYTES,
  a_payload_ver   INT2,
  a_leaf_hash     BYTES
) LANGUAGE PLpgSQL AS $proc$
DECLARE
  v_state       trappoint_ref.subject_state;
  v_head        INT8;
  v_epoch       INT8;
  v_open        INT8;
  v_prev_digest BYTES;
  v_clearance   BYTES;
  v_new_head    INT8;
BEGIN
  -- ── 1 · ANCHOR THE SUBJECT ───────────────────────────────────────────────────
  -- `FOR UPDATE` is LOCK ORDERING AND RETRY-THRASH REDUCTION ONLY, never
  -- correctness. Under SERIALIZABLE these locks are unreplicated and best-effort
  -- unless `enable_durable_locking_for_serializable` is set, and nothing here depends
  -- on them either way: correctness comes from SERIALIZABLE plus the compare-and-swap
  -- in step 5 plus the CHECKs in step 8.
  SELECT t.state, t.head_seq, t.gate_epoch
    INTO v_state, v_head, v_epoch
    FROM trappoint_ref.change_request t
   WHERE t.cr_id = a_subject_id
     FOR UPDATE;
  IF v_state IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT_REF: merge refused by trappoint_ref.merge_change_request'
                || ' — no change_request with that identifier';
  END IF;

  -- ── 2 · RE-DERIVE UNDER A SHARED LOCK ────────────────────────────────────────
  -- This is the anti-join of §6.5. It takes shared locks on the obligation rows so a
  -- concurrent materialisation conflicts here rather than after the CHECKs have
  -- passed (anomaly A1), and it produces the number the event payload records.
  --
  -- IT DOES NOT DECIDE. The refusal for a non-zero result belongs to
  -- cr_gate_closed_when_merged when the counter agrees, and to
  -- trappoint_ref.fn_cr_merge_gate when it does not — conformance cases CF-01,
  -- CF-02 and CF-03 name those two exhibits, and a refusal raised HERE would carry
  -- the name of this procedure instead, which is the wrong diagnosis for the right
  -- outcome.
  SELECT count(*) INTO v_open
    FROM (SELECT 1
            FROM trappoint_ref.blocking_check bc
           WHERE bc.cr_id = a_subject_id
             AND NOT EXISTS (
                   SELECT 1 FROM trappoint_ref.disposition d
                    WHERE d.check_id = bc.check_id
                      AND d.retracted_by IS NULL
                      AND (d.expires_at IS NULL OR d.expires_at > now()))
             FOR SHARE) AS locked;

  -- ── 3 · PROJECT THE PREDECESSOR CHAIN DIGEST ─────────────────────────────────
  -- The chain link is READ from the predecessor rather than accepted from the caller.
  -- `fn_cr_event_chain` verifies it on insert either way, so on this path the
  -- verification is tautological and on every OTHER writer's path it is the whole
  -- defence — which is the point of enforcing at the table rather than at the caller.
  -- A missing predecessor leaves this NULL, the genesis value goes in, and that
  -- trigger refuses with `P0001`: the gate does not invent a chain.
  SELECT e.chain_digest INTO v_prev_digest
    FROM trappoint_ref.cr_event e
   WHERE e.cr_id = a_subject_id AND e.seq = v_head;

  -- ── 4 · PROJECT THE CLEARANCE DIGEST ─────────────────────────────────────────
  -- SHA-256 over the sorted (check_id, disposition_id) set: exactly which obligations
  -- were cleared, and by which signatures, at the instant of the merge. Computed by
  -- the SERVER from the base tables, so the completion record cannot claim a
  -- clearance set the database does not hold. A subject with no obligations digests
  -- the empty string, which is a stable, checkable value rather than a NULL.
  SELECT digest(coalesce(string_agg(bc.check_id::STRING || ':' || d.disposition_id::STRING, '|'
                                    ORDER BY bc.check_id::STRING, d.disposition_id::STRING), ''),
                'sha256')
    INTO v_clearance
    FROM trappoint_ref.blocking_check bc
    JOIN trappoint_ref.disposition d
      ON d.check_id = bc.check_id AND d.retracted_by IS NULL
   WHERE bc.cr_id = a_subject_id;

  -- ── 5 · APPEND THE TRANSITION EVENT ──────────────────────────────────────────
  -- `23505` on the CAS means someone moved the head; `23503` on `legal_edge` means
  -- the edge state → 'merged' is not in the transition table (CF-13).
  -- `from_state` is the state actually read in step 1, never an assumed one, so an
  -- illegal transition is refused by data rather than by an assumption.
  --
  -- The payload carries what the gate OBSERVED, appended server-side to what the
  -- caller supplied. It is inside `chain_digest`, so the observation is chained.
  INSERT INTO trappoint_ref.cr_event
              (cr_id, seq, prev_seq, from_state, to_state, subject_kind,
               actor_sub, payload, prev_digest)
       VALUES (a_subject_id, v_head + 1, v_head, v_state, 'merged', 'change_request',
               a_merged_by,
               a_payload || jsonb_build_object('gate_observed_open', v_open,
                                               'gate_epoch', v_epoch),
               coalesce(v_prev_digest, decode(repeat('00', 32), 'hex')));

  -- ── 6 · PIN THE EPOCH ────────────────────────────────────────────────────────
  -- The composite foreign key (cr_id, gate_epoch) → trappoint_ref.change_request under
  -- ON UPDATE RESTRICT is what makes attaching a later obligation to a completed
  -- transition PHYSICALLY IMPOSSIBLE: every new obligation bumps gate_epoch, and the
  -- bump is refused while this row references the old value (MI07, anomaly A2).
  -- `merge_record_pkey` refuses a second merge of the same subject (CF-09, MI09).
  INSERT INTO trappoint_ref.merge_record
              (subject_kind, subject_id, cr_id, gate_epoch,
               merged_by, merged_commit, clearance_digest)
       VALUES ('change_request', a_subject_id, a_subject_id, v_epoch,
               a_merged_by, a_merged_commit, v_clearance);

  -- ── 7 · THE CUSTODY LEDGER — NOT RENDERED FOR THIS BINDING ───────────────────
  -- This arm writes trappoint_ref.ledger_intake and reads trappoint_ref.site, neither of
  -- which this binding declares or owns (`emit_outbox = false`, ruling D9). Procedures
  -- bind EARLY on v26.2, so naming an absent relation would make this migration
  -- un-appliable rather than degrade it; the switch is therefore at render time and
  -- this comment is the committed fallback a reviewer reads (ruling D5).
  --
  -- `a_actor_kind`, `a_canon_bytes`, `a_payload_ver` and `a_leaf_hash` are accepted
  -- and unused here ON PURPOSE. One ABI across every binding is worth more than four
  -- saved parameters: `trappoint_core.gate.execute_gate` issues one `CALL` shape, and
  -- a signature that varied by binding would put vertical knowledge into the client.

  -- ── 8 · THE LAST WRITE ───────────────────────────────────────────────────────
  -- Every CHECK on trappoint_ref.change_request fires HERE, on the completing row, and
  -- `fn_cr_merge_gate` runs immediately before them. `head_seq = v_head` is the
  -- compare-and-swap; `RETURNING … INTO` is how a zero-row UPDATE is detected, because
  -- `GET DIAGNOSTICS … ROW_COUNT` is unimplemented on this platform. A procedure that
  -- committed here having matched no row would leave a merge_record for a merge that
  -- never happened, which is why this is one of the only two refusals in the file.
  UPDATE trappoint_ref.change_request
     SET state = 'merged',
         head_seq = v_head + 1,
         merged_commit = a_merged_commit
   WHERE cr_id = a_subject_id AND head_seq = v_head
  RETURNING head_seq INTO v_new_head;
  IF v_new_head IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT_REF: merge refused by trappoint_ref.merge_change_request'
                || ' — the head moved under the gate transaction';
  END IF;
END $proc$;
