-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- ══════════════════════════════════════════════════════════════════════════════════════════════
--  MAINLINE · demo_permit.sql — ONE permit, in precisely the state in which the gate refuses
--  owner:    deploy / w2-cloud-database
--  target:   database `mainline_demo`, after the full chain and after demo_world.sql
--  applied:  scripts/deploy/seed_demo.py (idempotently, second)
-- ══════════════════════════════════════════════════════════════════════════════════════════════
--
--  ⚠ NO REAL INCIDENT. NO REAL SITE. NO REAL FATALITY.
--
--  Permit `DEMO-PTW-0001` is invented, as is everything it points at. It is pre-seeded so that
--  the demo begins at the moment somebody presses merge rather than at the moment somebody opens
--  a permit — which `verticals/mainline/demo/DEMO-HONESTY.md` §3 lists as STAGED. The permit's
--  existence is staged. **The gate evaluation is not**, and no part of this file touches the gate.
--
-- ──────────────────────────────────────────────────────────────────────────────────────────────
--  THE STATE THIS FILE PRODUCES, AND WHY EACH PART OF IT IS NECESSARY
--
--  After this file the database holds exactly one gated subject, and:
--
--    permit.state          = 'dispositioned'   the client's claim that everything is answered
--    permit.open_blocking  = 1                 written by the trigger, not by this file
--    blocking_check        = 1 row, severity 4, virulence 'blood_major'
--    disposition           = NO ROWS
--
--  `'dispositioned'` is what "open" means in this schema. `mainline.subject_state` has no member
--  called `open` — the alphabet is draft / checks_materialised / dispositioned / merged /
--  suspended / closed / abandoned (migration 0011) — and `dispositioned` is the state from which
--  `merged` is the next legal transition (`mainline.subject_transition`). It is also the state in
--  which the client is CLAIMING every obligation now carries a signed disposition.
--
--  It does not. That claim is exactly what the gate exists to disbelieve, and the whole demo is
--  the database checking it instead of believing it.
--
--  THE COUNTER IS NOT WRITTEN HERE. `permit.open_blocking` is incremented by the trigger
--  `check_materialised` (migration 0121 → `mainline.fn_check_materialised`, 0101) when the
--  blocking check is inserted. `scripts/proof/gate_refusal.py` writes that counter by hand
--  because 0121 could not apply on the tree it was written against — `mainline_ops.outbox` had no
--  producer. On this database 0121 applies, so the projection is the projection.
--  `scripts/deploy/seed_demo.py` VERIFIES that the counter reads 1 and that the trigger exists,
--  and records both in `evidence/deploy/cloud-seed.json`, because "the trigger wrote it" is a
--  claim and the evidence should carry its check.
--
-- ──────────────────────────────────────────────────────────────────────────────────────────────
--  WHAT SHOULD HAPPEN WHEN SOMEBODY MERGES THIS PERMIT
--
--    CALL mainline.merge_permit(...)
--      →  ERROR  23514  failed to satisfy CHECK constraint gate_closed_when_issued
--
--  and with `open_blocking` forced to zero out of band first:
--
--    CALL mainline.merge_permit(...)
--      →  ERROR  P0001  merge refused by mainline.fn_permit_merge_gate
--                       — re-derived open obligation count is 1 while the projected counter
--                         reads zero
--
--  and after one signed disposition against `dec0de00-0007-…`:
--
--    CALL mainline.merge_permit(...)
--      →  00000, and a `mainline.merge_record` row with a server-computed clearance digest.
--
--  A gate that always refuses is broken, not safe. The third outcome is why this file seeds a
--  permit that CAN be admitted rather than one that is structurally unmergeable.
--
-- ──────────────────────────────────────────────────────────────────────────────────────────────
--  IDEMPOTENCE
--
--  Fixed UUIDs, fixed timestamps, `ON CONFLICT DO NOTHING` everywhere. The two `permit_event`
--  rows are the only statements with a subquery in them, and they are guarded by
--  `WHERE NOT EXISTS` on their own primary key rather than by `ON CONFLICT`, because the second
--  event's `prev_digest` must read the first event's trigger-computed `chain_digest` and an
--  `INSERT ... SELECT` is the only shape that can.
-- ══════════════════════════════════════════════════════════════════════════════════════════════

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 1 · THE PERMIT
--
-- Inserted in `draft`, which is where a permit starts. §6 walks it forward through its own
-- hash-chained event log; nothing here sets `state` directly.
--
-- `site_role` is NOT supplied: `fn_site_role` projects it from `mainline.site`, which is what
-- makes the RLS scope token unforgeable by an inserter (P2, `RLS-MATRIX.yaml` policy `site_scope`).
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.permit (
  permit_id, site_id, site_role, external_ref, ref_name, opened_at, horizon_at
) VALUES (
  'dec0de00-0006-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',
  'demo_site',
  'DEMO-PTW-0001',
  'refs/permits/demo-0001',
  TIMESTAMPTZ '2026-08-02 00:00:00+00',
  TIMESTAMPTZ '2027-08-02 00:00:00+00'
)
ON CONFLICT DO NOTHING;

-- What the permit cites. `relies_on` is the relation the merge gate's authority-source check
-- (0115 §3) walks: for every cited (clause_uuid, commit_id) there must be a row in
-- `mainline.clause_blame_current`. `demo_world.sql` §6 seeded it.
INSERT INTO mainline.permit_clause (permit_id, clause_uuid, commit_id, relation)
VALUES (
  'dec0de00-0006-4000-8000-000000000001',
  'dec0de00-0004-4000-8000-000000000001',
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  'relies_on'
)
ON CONFLICT DO NOTHING;

-- THE CERTIFIED NULL (0115 §4, invariant I08). `unmodelled_asset_count = 0` means either
-- "certified zero" or "never computed", and no CHECK over an integer column can tell those apart.
-- So the gate demands the certificate ROW, and a permit whose boundary was never certified is
-- refused. Seeding it is what keeps the demo's refusal the one about obligations.
INSERT INTO mainline.boundary_certificate (
  permit_id, cert_gen, asset_graph_version,
  tags_declared, tags_resolved, tags_unmodelled, under_declared, computed_at
) VALUES (
  'dec0de00-0006-4000-8000-000000000001',
  1, 'demo-asset-graph-1',
  1, 1, 0, 0,
  TIMESTAMPTZ '2026-08-02 01:00:00+00'
)
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 2 · THE RECALL RUN THAT FOUND THE PRECURSOR
--
-- It lives here rather than in `demo_world.sql` because `mainline_meas.recall_run.permit_id` is
-- `NOT NULL REFERENCES mainline.permit` — a recall run in this schema is a permit-scoped fact and
-- cannot exist before its permit. CockroachDB validates foreign keys per statement and has no
-- deferrable constraints, so there is no ordering of the two seed files that puts this row in the
-- static corpus. That is the schema's decision, recorded rather than tidied away.
--
-- `mainline.fn_recall_policy_anchored` (0112, fired by 0136) refuses this INSERT unless
-- `demo-recall-1.0` is anchored inside a cosigned admissible checkpoint for this site. It is —
-- `demo_world.sql` §8 and §9 — so the trigger chain is walked rather than bypassed.
--
-- The SILENCE RECEIPT is the row worth reading twice. It records what the pass DECLINED to
-- surface: `s` of `n` candidates below `theta`, with a boundary proof. It is why "we found one
-- precursor" carries an arithmetic boundary instead of a claim of exhaustiveness, and
-- `mainline_audit.v_silence_summary` is the surface that reads it.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline_meas.recall_run (
  run_id, permit_id, site_id, corpus_commit, policy_version, index_plan_digest,
  index_generation, n_candidates, n_blocking, n_advisory, n_silenced, n_deduped, started_at
) VALUES (
  'dec0de00-0009-4000-8000-000000000001',
  'dec0de00-0006-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  'demo-recall-1.0',
  digest('mainline-demo/recall/index-plan', 'sha256'),
  'g1', 1, 1, 0, 0, 0,
  TIMESTAMPTZ '2026-08-02 03:00:00+00'
)
ON CONFLICT DO NOTHING;

INSERT INTO mainline_meas.silence_receipt (
  silence_receipt_id, run_id, permit_id, corpus_root, candidate_root,
  theta, s, n, boundary_proof, policy_version, issued_at
) VALUES (
  'dec0de00-000a-4000-8000-000000000001',
  'dec0de00-0009-4000-8000-000000000001',
  'dec0de00-0006-4000-8000-000000000001',
  digest('mainline-demo/recall/corpus-root', 'sha256'),
  digest('mainline-demo/recall/candidate-root', 'sha256'),
  0.35, 1, 1,
  '{"synthetic": true, "leaf_s": [], "leaf_s_plus_1": [],
    "source": "verticals/mainline/db/seeds/demo/demo_permit.sql"}'::JSONB,
  'demo-recall-1.0',
  TIMESTAMPTZ '2026-08-02 03:00:05+00'
)
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 3 · THE OBLIGATION — the one row this whole deployment exists to make undeniable
--
-- One open blocking check. `severity`, `virulence` and `closure_gen` are supplied here and are
-- IMMEDIATELY OVERWRITTEN by `fn_check_project` from `mainline.clause_blame_current` (invariant
-- MI25): they are inputs to nothing. The values that end up in the row are severity 4 and
-- virulence `blood_major`, projected from the closure `demo_world.sql` §6 wrote, and
-- `scripts/deploy/seed_demo.py` reads them back to prove the projection ran.
--
-- Inserting this row fires `check_materialised`, which takes `FOR UPDATE` on the permit,
-- increments `open_blocking` to 1, bumps `gate_epoch`, and writes a pointer-and-digest row into
-- `mainline_ops.outbox`. From this statement onward the permit cannot be merged.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.blocking_check (
  check_id, subject_kind, permit_id, site_id, clause_uuid, commit_id, precursor_event_id,
  origin, severity, virulence, closure_gen, recall_run_id, evidence_summary, materialised_at
) VALUES (
  'dec0de00-0007-4000-8000-000000000001',
  'permit',
  'dec0de00-0006-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',
  'dec0de00-0004-4000-8000-000000000001',
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  'dec0de00-0005-4000-8000-000000000001',
  'blame_ancestry',
  0, 'routine', 0,                       -- projected over by fn_check_project (MI25)
  'dec0de00-0009-4000-8000-000000000001',
  'SYNTHETIC — recalled precursor DEMO-INC-0001 reaches the clause version this permit relies on.',
  TIMESTAMPTZ '2026-08-02 03:00:10+00'
)
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 4 · THE EXPOSURE RECEIPT — what was actually put in front of a human
--
-- A disposition takes a composite foreign key onto the exact rows the same serializable
-- transaction returned. That is the mechanism behind DEMO-HONESTY.md §5: *"it never showed me"*
-- and *"I signed without looking"* cannot both be said.
--
-- ⚠ STAGED, AND SAY SO. In the product a receipt's TTL is hours — `mainline.exposure_receipt`
-- constrains only `expires_at > issued_at`, and the application picks the window. This seeded
-- receipt expires on 2027-01-01 so that the admission beat keeps working for every judge for the
-- whole judging period, rather than for two hours after somebody ran the deploy. That is a
-- demonstration convenience, it belongs in DEMO-HONESTY.md's STAGED column, and it is written
-- down here so nobody reads the long window as the product's default.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.exposure_receipt (
  receipt_id, subject_kind, permit_id, actor_sub, issued_at, issued_hlc, expires_at,
  corpus_root, silence_receipt_id, policy_version, total_tokens, receipt_digest
) VALUES (
  'dec0de00-0008-4000-8000-000000000001',
  'permit',
  'dec0de00-0006-4000-8000-000000000001',
  'demo.signer',
  TIMESTAMPTZ '2026-08-02 03:05:00+00',
  1,
  TIMESTAMPTZ '2027-01-01 00:00:00+00',
  digest('mainline-demo/recall/corpus-root', 'sha256'),
  'dec0de00-000a-4000-8000-000000000001',
  'demo-recall-1.0',
  200,
  digest('mainline-demo/receipt/dec0de00-0008', 'sha256')
)
ON CONFLICT DO NOTHING;

INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, tokens)
VALUES (
  'dec0de00-0008-4000-8000-000000000001',
  'dec0de00-0007-4000-8000-000000000001',
  digest('mainline-demo/exposure-line/dec0de00-0007', 'sha256'),
  200
)
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 5 · THE CLIENT'S CLAIM — two events on the permit's own hash chain
--
--   seq 1 :  draft               → checks_materialised
--   seq 2 :  checks_materialised → dispositioned
--
-- `chain_digest` is a STORED generated column, `digest(prev_digest || payload::STRING::BYTES,
-- 'sha256')`, so each link is computed by the database and cannot be supplied. `legal_edge` is a
-- foreign key onto `mainline.subject_transition`: an illegal transition is not refused by a rule,
-- it is NOT REPRESENTABLE.
--
-- The second edge is the client asserting that every obligation now carries a signed disposition.
-- There is no row in `mainline.disposition`. The database is about to find that out for itself.
--
-- `WHERE NOT EXISTS` rather than `ON CONFLICT DO NOTHING`: these are `INSERT ... SELECT`
-- statements, because seq 2's `prev_digest` has to read seq 1's generated `chain_digest`, and the
-- guard has to hold for the SELECT as well as for the write.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.permit_event (
  permit_id, seq, prev_seq, from_state, to_state, subject_kind, actor_sub, payload, prev_digest, at
)
SELECT
  'dec0de00-0006-4000-8000-000000000001',
  1, 0, 'draft', 'checks_materialised', 'permit', 'demo.signer',
  '{"synthetic": true, "to": "checks_materialised",
    "source": "verticals/mainline/db/seeds/demo/demo_permit.sql"}'::JSONB,
  '\x0000000000000000000000000000000000000000000000000000000000000000'::BYTES,
  TIMESTAMPTZ '2026-08-02 03:00:20+00'
WHERE NOT EXISTS (
  SELECT 1 FROM mainline.permit_event
   WHERE permit_id = 'dec0de00-0006-4000-8000-000000000001' AND seq = 1
);

INSERT INTO mainline.permit_event (
  permit_id, seq, prev_seq, from_state, to_state, subject_kind, actor_sub, payload, prev_digest, at
)
SELECT
  'dec0de00-0006-4000-8000-000000000001',
  2, 1, 'checks_materialised', 'dispositioned', 'permit', 'demo.signer',
  '{"synthetic": true, "to": "dispositioned",
    "source": "verticals/mainline/db/seeds/demo/demo_permit.sql"}'::JSONB,
  prior.chain_digest,
  TIMESTAMPTZ '2026-08-02 03:10:00+00'
FROM mainline.permit_event AS prior
WHERE prior.permit_id = 'dec0de00-0006-4000-8000-000000000001'
  AND prior.seq = 1
  AND NOT EXISTS (
    SELECT 1 FROM mainline.permit_event
     WHERE permit_id = 'dec0de00-0006-4000-8000-000000000001' AND seq = 2
  );

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 6 · MOVE THE HEAD
--
-- The event log is the record; `permit.state` and `permit.head_seq` are the projection of it.
-- Written last, and written to match the chain, so that a reader who does not trust the column
-- can recompute it from `mainline.permit_event` and get the same answer.
--
-- `open_blocking` is deliberately ABSENT from this UPDATE. The trigger owns that column.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

UPDATE mainline.permit
   SET state = 'dispositioned', head_seq = 2
 WHERE permit_id = 'dec0de00-0006-4000-8000-000000000001'
   AND head_seq < 2;

-- ══════════════════════════════════════════════════════════════════════════════════════════════
-- WHAT IS DELIBERATELY NOT HERE: a row in `mainline.disposition`.
--
-- That absence is the demonstration. Everything above is the history a real permit would carry;
-- the one thing missing is a human's signed answer to the one obligation the recall pass raised.
-- The gate refuses on exactly that, by name, with a SQLSTATE, and the refusal is the database's.
-- ══════════════════════════════════════════════════════════════════════════════════════════════
