-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
--
-- ══════════════════════════════════════════════════════════════════════════════════════════════
--  MAINLINE · demo_world.sql — the static corpus the demo's read surfaces show
--  owner:    deploy / w2-cloud-database
--  target:   database `mainline_demo` on CockroachDB Cloud `mainline-dev`, after the full chain
--  applied:  scripts/deploy/seed_demo.py (idempotently, before demo_permit.sql)
-- ══════════════════════════════════════════════════════════════════════════════════════════════
--
--  ⚠ NO REAL INCIDENT. NO REAL SITE. NO REAL FATALITY.
--
--  Every row below is synthetic and corresponds to nobody. The operator, the people, the
--  document, the clause and the incident are invented for this demonstration. This is the same
--  sentence `verticals/mainline/demo/DEMO-HONESTY.md` prints, restated at the point where the
--  synthetic data actually enters the database, because a disclosure that lives only in a
--  markdown file is a disclosure nobody reads at the moment it matters.
--
--  Every row is ALSO flagged synthetic in the data itself, by whatever means the schema permits:
--
--    * external references are prefixed `DEMO-`            (mainline.event.external_ref)
--    * free text opens with `SYNTHETIC —`                  (title, narrative, message, attribution)
--    * every JSONB payload carries `"synthetic": true` and names this file
--    * every provenance column names this file             (computed_by, projector_ver, wrote_as)
--    * every principal is prefixed `demo.`                 (person.signer_sub)
--
--  So a reader who never opens the documentation still cannot mistake this for production data,
--  and `SELECT ... WHERE narrative LIKE 'SYNTHETIC%'` is a census anyone can run.
--
-- ──────────────────────────────────────────────────────────────────────────────────────────────
--  WHY THIS IS SQL AND NOT PYTHON
--
--  `scripts/proof/gate_refusal.py` seeds the same history in Python and is the working reference
--  this file was derived from. It has to be Python: it decides at runtime whether a projection
--  trigger exists, and writes a counter by hand when it does not. This file has a different job —
--  a judge reads it. Every value is a literal, every digest is a `digest(...)` over a string that
--  says what it is, and there is no control flow to follow. What you can read here is what is in
--  the database.
--
-- ──────────────────────────────────────────────────────────────────────────────────────────────
--  IDEMPOTENCE
--
--  Fixed UUIDs, fixed timestamps, fixed digests, `ON CONFLICT DO NOTHING` on every statement.
--  Re-applying this file changes nothing and raises nothing. That property is not decoration: the
--  deploy is meant to be re-runnable during judging, and a seed that appends on every run would
--  make the demo's row counts a function of how many times somebody pressed deploy.
--
--  The UUIDs all begin `dec0de00`, which is hexadecimal and therefore legal, and which makes
--  every demo row greppable in a log by eight characters.
--
-- ──────────────────────────────────────────────────────────────────────────────────────────────
--  THE ONE SCHEMA QUIRK THIS FILE HAS TO HONOUR, RECORDED RATHER THAN WORKED AROUND
--
--  `mainline.fn_recall_policy_anchored` (migration 0112, fired by 0136 on `recall_run`) checks
--
--      WHERE cp.site_code = ((NEW).site_id)::STRING
--
--  so the custody ledger's partition key for a site is the site's own UUID rendered as text. That
--  is a property of the shipped function, not a convention this file chose, and so
--  `mainline.site.site_code` below is the literal text of `site_id`. Renaming the seam to make
--  the seed prettier would be seeding a different schema from the one that ships.
-- ══════════════════════════════════════════════════════════════════════════════════════════════

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 1 · THE SITE
--
-- `site_role` is the RLS scope token (`RLS-MATRIX.yaml`, policy `site_scope`:
-- `USING (site_role = CURRENT_USER)`). It is a NAME, it is UNIQUE, and it is projected onto
-- `mainline.permit` by `fn_site_role` — so an inserter cannot forge it (P2).
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver, opened_at)
VALUES (
  'dec0de00-0001-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',   -- = site_id::STRING, per fn_recall_policy_anchored
  'demo_site',
  'dec0de00-0002-4000-8000-000000000001',
  1,
  TIMESTAMPTZ '2026-01-05 00:00:00+00'
)
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 2 · THE PEOPLE, AND THE CREDENTIALS THAT BIND THEIR SIGNATURES
--
-- Two people, because a disposition on a `blood_major` obligation takes a countersignature. Both
-- are fictional. `competency_snapshot` is FROZEN at the moment of signing by
-- `fn_disposition_project`; what is seeded here is the authoritative row it will copy from, which
-- is why the authorisations are stated rather than implied.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.person (
  signer_sub, effective_from, org, rank,
  competency_source_id, competency_sha256, competency_snapshot,
  identity_source, enrolment_assurance
) VALUES
  (
    'demo.signer',
    TIMESTAMPTZ '2026-01-05 00:00:00+00',
    'demo-operator', 5,
    'dec0de00-000b-4000-8000-000000000001',
    digest('mainline-demo/competency/demo.signer', 'sha256'),
    '{"synthetic": true, "authorisations": ["ISOLATION_AUTHORITY"], "training": ["LOTO-3"],
      "source": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
    'hr_system_of_record', 'hr_system_of_record'
  ),
  (
    'demo.countersigner',
    TIMESTAMPTZ '2026-01-05 00:00:00+00',
    'demo-assurer', 5,
    'dec0de00-000b-4000-8000-000000000002',
    digest('mainline-demo/competency/demo.countersigner', 'sha256'),
    '{"synthetic": true, "authorisations": ["ISOLATION_AUTHORITY"], "training": ["LOTO-3"],
      "source": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
    'hr_system_of_record', 'hr_system_of_record'
  )
ON CONFLICT DO NOTHING;

INSERT INTO mainline.signing_credential (
  credential_id, signer_sub, public_key_cose, aaguid, transports, attachment,
  enrolled_at, enrolment_assurance
) VALUES
  (
    digest('mainline-demo/credential/demo.signer', 'sha256'),
    'demo.signer',
    digest('mainline-demo/cose/demo.signer', 'sha256'),
    substring(digest('mainline-demo/aaguid/demo.signer', 'sha256') FROM 1 FOR 16),
    ARRAY['usb'], 'cross-platform',
    TIMESTAMPTZ '2026-01-06 00:00:00+00', 'hr_system_of_record'
  ),
  (
    digest('mainline-demo/credential/demo.countersigner', 'sha256'),
    'demo.countersigner',
    digest('mainline-demo/cose/demo.countersigner', 'sha256'),
    substring(digest('mainline-demo/aaguid/demo.countersigner', 'sha256') FROM 1 FOR 16),
    ARRAY['usb'], 'cross-platform',
    TIMESTAMPTZ '2026-01-06 00:00:00+00', 'hr_system_of_record'
  )
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 3 · THE COMMIT DAG
--
-- Two commits and the edge between them. `commit_id` is a SHA-256 and the schema enforces the
-- length, so these are `digest(...)` over strings that say what each commit is — nobody can
-- choose a commit id in the real system either, and a hand-typed hex constant would look like
-- somebody had.
--
-- The DAG is what carries long-horizon history. It is NOT `AS OF SYSTEM TIME`: the measured GC
-- window on this cluster is 4500 seconds, and the demo's ancestry reaches back years. Every date
-- on screen is a column value.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.commit_obj (
  commit_id, site_id, gen, ref_name, committed_at, author_sub, message, envelope, envelope_bytes
) VALUES
  (
    digest('mainline-demo/commit/root', 'sha256'),
    'dec0de00-0001-4000-8000-000000000001',
    1, 'refs/heads/main',
    TIMESTAMPTZ '2026-01-07 00:00:00+00',
    'demo.signer',
    'SYNTHETIC — demo tenant established',
    '{"kind": "demo-genesis", "synthetic": true,
      "source": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
    '{"kind":"demo-genesis","source":"verticals/mainline/db/seeds/demo/demo_world.sql","synthetic":true}'::BYTES
  ),
  (
    digest('mainline-demo/commit/clause-v1', 'sha256'),
    'dec0de00-0001-4000-8000-000000000001',
    2, 'refs/heads/main',
    TIMESTAMPTZ '2026-01-08 00:00:00+00',
    'demo.signer',
    'SYNTHETIC — the clause version the demo permit relies on',
    '{"kind": "demo-clause-version", "synthetic": true,
      "clause": "dec0de00-0004-4000-8000-000000000001",
      "source": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
    '{"clause":"dec0de00-0004-4000-8000-000000000001","kind":"demo-clause-version","source":"verticals/mainline/db/seeds/demo/demo_world.sql","synthetic":true}'::BYTES
  )
ON CONFLICT DO NOTHING;

INSERT INTO mainline.commit_edge (child_id, parent_ord, parent_id, parent_gen)
VALUES (
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  0,
  digest('mainline-demo/commit/root', 'sha256'),
  1
)
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 4 · THE DOCUMENT, THE CLAUSE AND ITS VERSION
--
-- `sev_max = 4` and `anchor_set` are what make this clause reachable by the blame spine below.
-- `blood_root` is thirty-two zero bytes — the schema's legal "no ancestry yet" value, which the
-- closure in §6 then supersedes.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.doc (doc_id, site_id, doc_code, title, state, open_token_count)
VALUES (
  'dec0de00-0003-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',
  'DEMO-SOP-0001',
  'SYNTHETIC — Isolation of stored energy',
  'live', 0
)
ON CONFLICT DO NOTHING;

INSERT INTO mainline.clause (clause_uuid, site_id, birth_commit, activity_root, head_commit)
VALUES (
  'dec0de00-0004-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  'demo/isolation',
  digest('mainline-demo/commit/clause-v1', 'sha256')
)
ON CONFLICT DO NOTHING;

-- ⚠ `WHERE NOT EXISTS`, NOT `ON CONFLICT DO NOTHING`, AND THE DIFFERENCE IS NOT STYLE.
-- `clause_version` carries a BEFORE INSERT trigger (`z_delta_witness_required`), and a BEFORE
-- trigger runs BEFORE conflict resolution: `ON CONFLICT DO NOTHING` cannot suppress an exception
-- a trigger has already raised. Measured on the sibling table `clause_blame_closure`, where a
-- second run of this file raised `P0001 closure generations must be dense and monotone` and
-- aborted the whole batch. Every seeded table whose INSERT fires a BEFORE trigger that can raise
-- therefore uses the `INSERT ... SELECT ... WHERE NOT EXISTS` form, which never offers the row.
INSERT INTO mainline.clause_version (
  clause_uuid, gen, commit_id, site_id, doc_id, activity_root, ordinal, printed_label,
  raw_text, canon_text, canon_version, canon_sha256, anchor_set, cat_confidence,
  control_delta, delta_basis, blood_root, blood_peaks, blood_size, sev_max
)
SELECT
  'dec0de00-0004-4000-8000-000000000001',
  1,
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  'dec0de00-0001-4000-8000-000000000001',
  'dec0de00-0003-4000-8000-000000000001',
  'demo/isolation',
  1, '7.3.2(b)',
  'SYNTHETIC — Before any intrusive work, stored energy shall be isolated, locked and verified at zero by a competent person.',
  'SYNTHETIC — Before any intrusive work, stored energy shall be isolated, locked and verified at zero by a competent person.',
  1,
  digest('SYNTHETIC — Before any intrusive work, stored energy shall be isolated, locked and verified at zero by a competent person.', 'sha256'),
  ARRAY['LOTO', 'ZERO_ENERGY'],
  'ok', 'introduce', 'lattice',
  '\x0000000000000000000000000000000000000000000000000000000000000000'::BYTES,
  ARRAY[]::BYTES[], 0, 4
WHERE NOT EXISTS (
  SELECT 1 FROM mainline.clause_version
   WHERE clause_uuid = 'dec0de00-0004-4000-8000-000000000001' AND gen = 1
);

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 5 · THE PRECURSOR
--
-- A severity-4 incident whose ancestry reaches the clause the permit relies on. In the demo's
-- narrative this is the fact the recall pass FOUND AFTER the permit was drafted — which is the
-- whole reason there is an obligation to dispose of.
--
-- It is invented. `occurred_at` is 2019 so that the ancestry the demo shows is genuinely
-- long-horizon, and 2019 is far outside any garbage-collection window on any tier — which is the
-- point being made: the history is in the commit DAG and in this row, not in MVCC.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.event (
  event_id, site_id, external_ref, occurred_at, ingested_at, kind, title, narrative,
  source_doc_id, source_object_key, source_sha256,
  severity_actual, severity_potential, severity_gate, severity_basis, canon_version
) VALUES (
  'dec0de00-0005-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',
  'DEMO-INC-0001',
  TIMESTAMPTZ '2019-03-14 06:20:00+00',
  TIMESTAMPTZ '2026-08-01 00:00:00+00',
  'incident',
  'SYNTHETIC — Stored energy release during intrusive work',
  'SYNTHETIC — An isolation was signed off without verification at zero; residual hydraulic '
  'pressure released while the guard was removed. No real incident, no real site, no real '
  'fatality: this narrative was written for the MAINLINE demonstration and describes nobody.',
  'dec0de00-0003-4000-8000-000000000001',
  'demo/incident-0001.pdf',
  digest('mainline-demo/incident/DEMO-INC-0001', 'sha256'),
  4, 4, 4, 'human_rated', 1
)
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 6 · THE BLAME SPINE
--
-- The edge says this incident names this clause. The closure is the PROJECTION the gate reads:
-- one ancestor, severity 4, banded `blood_major`. `fn_closure_guard` demands the first closure
-- generation for a clause version be zero and ledgers the closure in the same transaction, so
-- both happen here, unhelped.
--
-- `mainline.clause_blame_current` — the view the merge gate consults for its authority-source
-- check (0115 §3) — is derived from this row. Without it the gate refuses with `P0001` naming an
-- unbacked cited clause version, which is a DIFFERENT refusal from the one the demo is about.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.blame_edge (
  event_id, clause_uuid, basis, state, site_id, commit_id,
  features, attribution, evidence_doc_id, evidence_quote_sha256
) VALUES (
  'dec0de00-0005-4000-8000-000000000001',
  'dec0de00-0004-4000-8000-000000000001',
  'asserted_document', 'active',
  'dec0de00-0001-4000-8000-000000000001',
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  '{"synthetic": true, "quote_offsets": [0, 96], "source": "demo investigation report, §4",
    "seed": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
  'SYNTHETIC — the investigation names this clause as the control that failed.',
  'dec0de00-0003-4000-8000-000000000001',
  digest('mainline-demo/quote/DEMO-INC-0001', 'sha256')
)
ON CONFLICT DO NOTHING;

-- `WHERE NOT EXISTS` for the reason given above `clause_version`: `fn_closure_guard` is a BEFORE
-- INSERT trigger and it raises `P0001 closure generations must be dense and monotone` when a
-- second run offers it generation 0 again. That is the guard working correctly — closure_gen 0
-- has already been used for this (clause, commit) — so the seed must not offer the row at all.
INSERT INTO mainline.clause_blame_closure (
  clause_uuid, as_of_commit, closure_gen, site_id,
  ancestor_events, ancestor_count, max_severity, virulence, depth, truncated,
  computed_by, projector_ver
)
SELECT
  'dec0de00-0004-4000-8000-000000000001',
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  0,
  'dec0de00-0001-4000-8000-000000000001',
  ARRAY['dec0de00-0005-4000-8000-000000000001']::UUID[],
  1, 4, 'blood_major', 1, false,
  'verticals/mainline/db/seeds/demo/demo_world.sql', 'demo-1'
WHERE NOT EXISTS (
  SELECT 1 FROM mainline.clause_blame_closure
   WHERE clause_uuid = 'dec0de00-0004-4000-8000-000000000001'
     AND as_of_commit = digest('mainline-demo/commit/clause-v1', 'sha256')
);

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 7 · THE BLAME ACCOUNT FOR THE CITED COMMIT
--
-- `z_cbm_gate` refuses a merge whose cited commit has no account, and refuses again if the
-- account disagrees with live residue. Nothing in this world is residue, so the account is a
-- balanced zero — which is a claim the conservation view `mainline_audit.v_cbm_ledger` can be
-- asked to confirm on camera.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

-- `WHERE NOT EXISTS` again: `z_cbm_account_guard` is a BEFORE INSERT trigger over the same
-- generation-density idiom as the closure guard.
INSERT INTO mainline.cbm_account (
  site_id, commit_id, account_gen, inherited, carried, split_carried, merge_carried,
  residue_open, residue_disposed, computed_by, wrote_as, projector_ver
)
SELECT
  'dec0de00-0001-4000-8000-000000000001',
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  0, 0, 0, 0, 0, 0, 0,
  'verticals/mainline/db/seeds/demo/demo_world.sql', current_user, 'demo-1'
WHERE NOT EXISTS (
  SELECT 1 FROM mainline.cbm_account
   WHERE site_id = 'dec0de00-0001-4000-8000-000000000001'
     AND commit_id = digest('mainline-demo/commit/clause-v1', 'sha256')
);

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 8 · THE CUSTODY ANCHOR
--
-- A recall run may not cite an unanchored policy, and a policy's anchor must sit inside a
-- COSIGNED, admissible checkpoint (`fn_recall_policy_anchored`, migration 0112). So the
-- checkpoint and its witness signature are seeded before the policy that leans on them, and the
-- trigger chain is walked rather than bypassed.
--
-- The witness here is our own; `DEMO-HONESTY.md` §4 already says adverse witnesses are not
-- running, and this row does not change that. `adverse = true` is the column's declared value for
-- a witness in a different trust domain, and the honest reading of this seed is "the mechanism is
-- exercised", never "an independent party signed this".
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.ledger_checkpoint (
  site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256, admissible, issued_at
) VALUES (
  'dec0de00-0001-4000-8000-000000000001',
  1,
  digest('mainline-demo/ledger/root/1', 'sha256'),
  'mainline/dec0de00-0001-4000-8000-000000000001' || chr(10) || '1' || chr(10)
    || encode(digest('mainline-demo/ledger/root/1', 'sha256'), 'hex') || chr(10),
  '{"synthetic": true, "drand_round": 1, "nist_pulse": 1,
    "source": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
  digest('mainline-demo/ledger/logsig/1', 'sha256'),
  digest('mainline-demo/ledger/canon-src', 'sha256'),
  true,
  TIMESTAMPTZ '2026-08-01 01:00:00+00'
)
ON CONFLICT DO NOTHING;

INSERT INTO mainline.cosignature (
  site_code, tree_size, witness_id, trust_domain, adverse, sig, received_at
) VALUES (
  'dec0de00-0001-4000-8000-000000000001',
  1,
  'witness.demo/hsr-1', 'union_hsr', true,
  digest('mainline-demo/ledger/cosig/1', 'sha256'),
  TIMESTAMPTZ '2026-08-01 01:05:00+00'
)
ON CONFLICT DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 9 · THE RECALL POLICY THE PASS RAN UNDER
--
-- The policy names the models it used, which is what makes the run reproducible in principle;
-- `amazon.titan-embed-text-v2:0` is the embedding model this deployment actually calls in AWS
-- Bedrock (`ap-southeast-2`).
--
-- WHERE THE RUN ITSELF IS, AND WHY IT IS NOT HERE. `mainline_meas.recall_run.permit_id` is
-- `NOT NULL REFERENCES mainline.permit`, so a recall run cannot exist before its permit does — a
-- run in this schema is a permit-scoped fact, not a corpus-scoped one. CockroachDB validates
-- foreign keys per statement and has no deferrable constraints, so there is no ordering of these
-- two files that puts the run in the static corpus. The run, its silence receipt and the
-- obligation they produced are therefore seeded by `demo_permit.sql`, immediately after the
-- permit row. Splitting it that way is the schema's decision; saying so here is this file's.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline_meas.recall_policy (
  policy_version, taxonomy_ver, embed_model, gen_model, prompt_version, beam_size,
  tau, arms, calibration_set_sha256, author_sub, signature,
  anchored_tree_size, anchored_at, committed_at
) VALUES (
  'demo-recall-1.0', 1,
  'amazon.titan-embed-text-v2:0', 'au.anthropic.claude', 'demo-p-1', 8,
  '{"tau0": 5, "rho": 4}'::JSONB,
  '{"lexical": true, "vector": true}'::JSONB,
  digest('mainline-demo/recall/calibration', 'sha256'),
  'demo.signer',
  digest('mainline-demo/recall/policy-signature', 'sha256'),
  1,
  TIMESTAMPTZ '2026-08-01 02:00:00+00',
  TIMESTAMPTZ '2026-08-01 02:00:00+00'
)
ON CONFLICT DO NOTHING;

-- ══════════════════════════════════════════════════════════════════════════════════════════════
-- END OF THE STATIC CORPUS.
--
-- What exists after this file: one site, two people with credentials, a two-commit DAG, one
-- document, one clause and its version, one severity-4 precursor, the blame edge and closure that
-- bind the two, a balanced blame account, a cosigned custody checkpoint, and the anchored recall
-- policy. Nothing here is gated and nothing here refuses anything — this is the *history*.
--
-- `demo_permit.sql` adds the single thing that makes the history decidable: a permit that relies
-- on that clause version, and one open obligation nobody has disposed of.
-- ══════════════════════════════════════════════════════════════════════════════════════════════
