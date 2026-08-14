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
--
-- THE PROBE READS THE VIEW (DM-9), AND HERE THAT IS EXACT RATHER THAN MERELY PERMITTED.
-- `mainline.clause_blame_current` is `DISTINCT ON (clause_uuid, as_of_commit)` over these same
-- rows, so it emits exactly one row for a pair the table holds at least one row for and no row for
-- a pair it holds none for: `EXISTS` has the same value over either relation, for every state the
-- table can be in. The reason to write the view anyway is that the equality above is a property of
-- `EXISTS`, not of this query — the moment anyone extends this probe to read a COLUMN (`AND
-- max_severity >= 4`, `AND ancestor_events @> …`) the two relations diverge, and the raw-table form
-- answers from whichever generation the scan reached first. Once a recomputation has appended
-- generation 1 that is a REAL row from a generation computed with LESS ancestry, so a LOWER
-- `max_severity`, with no error and no warning. DM-9 removes the wrong query from the vocabulary
-- rather than trusting the next editor of this seed to notice the difference.
--
-- THE INSERT BELOW NAMES THE RAW RELATION, AND THAT IS A RECORDED DM-9 AMENDMENT, NOT AN OVERSIGHT.
-- There is nowhere else to write it: the view is a `DISTINCT ON` projection and is not insertable,
-- and the sanctioned writer `verticals/mainline/db/queries/closure_write.sql` is a parameterised
-- top-level statement into which the projector binds ten positional values — a seed file that
-- `scripts/deploy/seed_demo.py` applies as ONE text cannot call it. `grep_closure_readpath.py`
-- names this exact path in `WRITE_ALLOWLIST` with its reason, and `docs/leads/datamodel.md` DM-9
-- carries the matching entry. The write is still policed inside the cluster: `fn_closure_guard`
-- (0108) refuses a non-dense generation with `P0001`, and `0128j`'s append-only weld refuses any
-- UPDATE or DELETE, so what this seed can do to the closure is append a first generation or fail.
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
  SELECT 1 FROM mainline.clause_blame_current
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
-- 8 · THE CUSTODY LEDGER, AND THE CHECKPOINTS THAT COMMIT TO IT
--
-- WHAT THIS SECTION USED TO DO, AND WHY THAT WAS A DEFECT RATHER THAN A THIN SEED.
--
-- Until 2026-08-14 this section seeded ONE checkpoint, `tree_size = 1`, with a `root_hash` of
-- `digest('mainline-demo/ledger/root/1', 'sha256')` — a hash of a STRING NAMING ITSELF — over a
-- `mainline.ledger_leaf` that held zero rows. `mainline.ledger_node` held zero rows too. So the
-- demo's transparency log published a signed commitment to a tree of size one with NOTHING
-- BEHIND IT, in the one surface whose entire purpose is that claims have something behind them.
-- A judge who clicked "verify" got an inclusion-proof array that was empty because the reader
-- (`reads.read_ledger`) correctly refuses to emit a proof over a window it cannot cover — so the
-- console's honesty machinery was the only thing standing between that row and a false exhibit.
--
-- That is not a decoration to be tidied. `docs/decisions/demo-ledger-seeding.md` records the
-- ruling and the evidence. This section now seeds a REAL four-leaf log.
--
-- ⚠ EVERY HASH BELOW IS COMPUTED BY THE DATABASE. NOT ONE IS TYPED.
--
-- This is the whole point, and it is the rule this repository has already been burned for
-- breaking once (see `tests/ci/test_demo_seed_is_frozen.py`, and the credential enrolment on the
-- line this file's §2 marks). The temptation in a seed like this is to run the arithmetic
-- offline, paste sixty-four hex characters per row, and get a green. That would be hand-rolling
-- a transparency log — a chain of numbers nobody can recompute, which is the exact property an
-- evidentiary hash must not have. So:
--
--   * `leaf_hash`      = `digest(0x00 || canon_bytes)`, computed here from the canonical bytes,
--                        per RFC 6962 §2.1 leaf-domain separation.
--   * `prev_link_hash` \  computed by `mainline.fn_ledger_cas_append` (migration 0119), the
--   * `link_hash`      /  product's OWN gap-free compare-and-swap appender. This file does not
--                        INSERT into `mainline.ledger_leaf` at all. `seq` is derived in-txn as
--                        `coalesce(max(seq)+1, 0)`, genesis `prev_link_hash` is 32 zero bytes and
--                        not NULL (custody CU-1), and the two UNIQUE constraints that make a fork
--                        physically impossible are walked rather than bypassed.
--   * interior nodes   = `digest(0x01 || left || right)`, read back OUT of the leaves the
--                        appender wrote.
--   * checkpoint roots = read back OUT of `mainline.ledger_node`. The `tree_size = 2` root IS
--                        node (1,0); the `tree_size = 4` root IS node (2,0). Storing the root as
--                        a node and then reading it into the checkpoint means the redundancy is
--                        CHECKABLE — `SELECT` them and compare — instead of two independent
--                        assertions that happen to agree.
--
-- THE ONE THING SQL CANNOT DO, STATED RATHER THAN HIDDEN. `canon_bytes` is RFC 8785 JCS and is
-- produced by the CLIENT (`trappoint_jcs.canon_v1`); migration 0072's header says so and says
-- DO NOT COMPUTE `leaf_hash` IN SQL. That prohibition names two failure modes — CockroachDB's
-- `sha256()` returns a hex STRING rather than BYTES (cockroach#73896), and JSONB normalises and
-- reorders keys, so `sha256(payload::STRING)` is a value no third party reproduces. NEITHER
-- applies here: `digest(...)` returns BYTES, and the hash below is taken over the literal
-- `canon_bytes` — never over `payload`. The canonicalisation itself is not performed in SQL; the
-- canonical bytes are written out longhand, sorted and whitespace-free, and `payload` is CAST
-- FROM THE SAME LITERAL so the two cannot drift. Each literal was verified to be byte-identical
-- to `canon_v1.canonicalise_payload()` of that object; the check is reproducible and is recorded
-- in `docs/decisions/demo-ledger-seeding.md` §4.
--
-- WHY FOUR LEAVES AND WHY CHECKPOINTS AT 2 AND 4. The four leaves are the four custody-relevant
-- facts THIS FILE has already established, in the order it established them: the document (§4),
-- the clause version (§4), the precursor event (§5) and the blame closure (§6). Nothing is
-- forward-referenced — every `subject_id` names a row that exists by the time this section runs.
-- Two checkpoints exist because a log that has checkpointed once cannot demonstrate CONSISTENCY;
-- RFC 6962 §2.1.2 is the check that catches delete-leaf-k-and-renumber, and it needs two tree
-- sizes to be a check at all. A log that publishes at 2 and again at 4 is a log behaving
-- normally, and it is what the in-browser verifier is built to consume.
--
-- WHAT THE CHECKPOINT ROW STILL DOES NOT PROVE. `log_sig`, `tsa_token` and `beacon` remain
-- synthetic and are marked so. A real checkpoint's value is that it LEFT the trust boundary
-- before we could change our minds about the tree; these did not. `canon_src_sha256` is likewise
-- a named placeholder rather than the live hash of the canonicaliser source, because a seed that
-- pinned that hash would go red on any edit to a file it does not own. What IS now true, and was
-- not before, is that `root_hash` commits to leaves that exist and that anyone can recompute.
--
-- The witness here is our own; `DEMO-HONESTY.md` §4 already says adverse witnesses are not
-- running, and this row does not change that. `adverse = true` is the column's declared value for
-- a witness in a different trust domain, and the honest reading of this seed is "the mechanism is
-- exercised", never "an independent party signed this".
--
-- A recall run may not cite an unanchored policy, and a policy's anchor must sit inside a
-- COSIGNED, admissible checkpoint (`fn_recall_policy_anchored`, migration 0112). So the
-- checkpoints and their witness signatures are seeded before the policy that leans on them, and
-- the trigger chain is walked rather than bypassed. §9's `anchored_tree_size = 1` is satisfied by
-- both checkpoints below, since 0112 asks for `cp.tree_size >= anchored_size`.
--
-- IDEMPOTENCE, WHICH IS SHARPER HERE THAN ANYWHERE ELSE IN THIS FILE. An APPENDER is by
-- definition not idempotent: calling `fn_ledger_cas_append` twice appends twice, and the demo's
-- row counts would become a function of how many times somebody pressed deploy. Fixed
-- `entry_id`s make `ledger_leaf_entry_unique` refuse the replay — but refusing means 23505, and
-- an exception aborts the whole batch. So every append below is GUARDED by an anti-join against
-- `mainline.ledger_leaf`: on a second run the guard selects zero rows and the function is never
-- called. `ON CONFLICT DO NOTHING` cannot be used for this, because the function's INSERT is
-- inside a PL/pgSQL body where this file's `ON CONFLICT` clause does not reach.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

-- 8.1 · THE FOUR INTAKE ENTRIES
--
-- `canon_bytes` is the evidence; `payload` is the human rendering and is NEVER hashed. Both are
-- cast from the SAME single-quoted literal `c.j`, which is what makes a substitution between them
-- impossible to introduce by editing one and forgetting the other. `hlc` is ADVISORY and nothing
-- may read it (migration 0072a puts that sentence in the database itself), so a fixed literal is
-- correct here and `cluster_logical_timestamp()` would only make this file non-deterministic.

INSERT INTO mainline.ledger_intake (
  entry_id, site_code, entry_kind, subject_id, actor, actor_kind,
  payload, canon_bytes, payload_ver, leaf_hash, is_sandbox, hlc, recorded_at
)
SELECT
  'dec0de00-000e-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',
  'doc_registered',
  'dec0de00-0003-4000-8000-000000000001',
  'verticals/mainline/db/seeds/demo/demo_world.sql',
  'service',
  c.j::JSONB,
  c.j::BYTES,
  1,
  digest(decode('00', 'hex') || c.j::BYTES, 'sha256'),
  false,
  1,
  TIMESTAMPTZ '2026-08-01 00:10:00+00'
FROM (
  SELECT '{"doc_id":"dec0de00-0003-4000-8000-000000000001","entry_kind":"doc_registered","site_code":"dec0de00-0001-4000-8000-000000000001","source":"verticals/mainline/db/seeds/demo/demo_world.sql","synthetic":true}' AS j
) AS c
WHERE NOT EXISTS (
  SELECT 1 FROM mainline.ledger_intake
   WHERE entry_id = 'dec0de00-000e-4000-8000-000000000001'
);

INSERT INTO mainline.ledger_intake (
  entry_id, site_code, entry_kind, subject_id, actor, actor_kind,
  payload, canon_bytes, payload_ver, leaf_hash, is_sandbox, hlc, recorded_at
)
SELECT
  'dec0de00-000e-4000-8000-000000000002',
  'dec0de00-0001-4000-8000-000000000001',
  'clause_version_committed',
  'dec0de00-0004-4000-8000-000000000001',
  'verticals/mainline/db/seeds/demo/demo_world.sql',
  'service',
  c.j::JSONB,
  c.j::BYTES,
  1,
  digest(decode('00', 'hex') || c.j::BYTES, 'sha256'),
  false,
  2,
  TIMESTAMPTZ '2026-08-01 00:20:00+00'
FROM (
  SELECT '{"clause_uuid":"dec0de00-0004-4000-8000-000000000001","entry_kind":"clause_version_committed","gen":1,"site_code":"dec0de00-0001-4000-8000-000000000001","source":"verticals/mainline/db/seeds/demo/demo_world.sql","synthetic":true}' AS j
) AS c
WHERE NOT EXISTS (
  SELECT 1 FROM mainline.ledger_intake
   WHERE entry_id = 'dec0de00-000e-4000-8000-000000000002'
);

INSERT INTO mainline.ledger_intake (
  entry_id, site_code, entry_kind, subject_id, actor, actor_kind,
  payload, canon_bytes, payload_ver, leaf_hash, is_sandbox, hlc, recorded_at
)
SELECT
  'dec0de00-000e-4000-8000-000000000003',
  'dec0de00-0001-4000-8000-000000000001',
  'precursor_event_ingested',
  'dec0de00-0005-4000-8000-000000000001',
  'verticals/mainline/db/seeds/demo/demo_world.sql',
  'service',
  c.j::JSONB,
  c.j::BYTES,
  1,
  digest(decode('00', 'hex') || c.j::BYTES, 'sha256'),
  false,
  3,
  TIMESTAMPTZ '2026-08-01 00:30:00+00'
FROM (
  SELECT '{"entry_kind":"precursor_event_ingested","event_id":"dec0de00-0005-4000-8000-000000000001","site_code":"dec0de00-0001-4000-8000-000000000001","source":"verticals/mainline/db/seeds/demo/demo_world.sql","synthetic":true}' AS j
) AS c
WHERE NOT EXISTS (
  SELECT 1 FROM mainline.ledger_intake
   WHERE entry_id = 'dec0de00-000e-4000-8000-000000000003'
);

INSERT INTO mainline.ledger_intake (
  entry_id, site_code, entry_kind, subject_id, actor, actor_kind,
  payload, canon_bytes, payload_ver, leaf_hash, is_sandbox, hlc, recorded_at
)
SELECT
  'dec0de00-000e-4000-8000-000000000004',
  'dec0de00-0001-4000-8000-000000000001',
  'blame_closure_computed',
  'dec0de00-0004-4000-8000-000000000001',
  'verticals/mainline/db/seeds/demo/demo_world.sql',
  'service',
  c.j::JSONB,
  c.j::BYTES,
  1,
  digest(decode('00', 'hex') || c.j::BYTES, 'sha256'),
  false,
  4,
  TIMESTAMPTZ '2026-08-01 00:40:00+00'
FROM (
  SELECT '{"clause_uuid":"dec0de00-0004-4000-8000-000000000001","closure_gen":0,"entry_kind":"blame_closure_computed","site_code":"dec0de00-0001-4000-8000-000000000001","source":"verticals/mainline/db/seeds/demo/demo_world.sql","synthetic":true}' AS j
) AS c
WHERE NOT EXISTS (
  SELECT 1 FROM mainline.ledger_intake
   WHERE entry_id = 'dec0de00-000e-4000-8000-000000000004'
);

-- 8.2 · SEQUENCING THEM — through the product's own appender, one position at a time
--
-- Four separate statements, in order, because `seq` is derived from `max(seq)` INSIDE the
-- transaction: a single set-returning call over four intake rows would leave the order of the
-- side effects to the optimiser, and this log's whole claim is that its order is not incidental.
-- The `batch_id` records which sequencer run produced the leaf and commits to nothing.

SELECT mainline.fn_ledger_cas_append(
         'dec0de00-0001-4000-8000-000000000001', i.entry_id, i.leaf_hash,
         'dec0de00-000f-4000-8000-000000000001'::UUID)
  FROM mainline.ledger_intake i
 WHERE i.entry_id = 'dec0de00-000e-4000-8000-000000000001'
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_leaf l
      WHERE l.site_code = 'dec0de00-0001-4000-8000-000000000001'
        AND l.entry_id = i.entry_id
   );

SELECT mainline.fn_ledger_cas_append(
         'dec0de00-0001-4000-8000-000000000001', i.entry_id, i.leaf_hash,
         'dec0de00-000f-4000-8000-000000000001'::UUID)
  FROM mainline.ledger_intake i
 WHERE i.entry_id = 'dec0de00-000e-4000-8000-000000000002'
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_leaf l
      WHERE l.site_code = 'dec0de00-0001-4000-8000-000000000001'
        AND l.entry_id = i.entry_id
   );

SELECT mainline.fn_ledger_cas_append(
         'dec0de00-0001-4000-8000-000000000001', i.entry_id, i.leaf_hash,
         'dec0de00-000f-4000-8000-000000000002'::UUID)
  FROM mainline.ledger_intake i
 WHERE i.entry_id = 'dec0de00-000e-4000-8000-000000000003'
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_leaf l
      WHERE l.site_code = 'dec0de00-0001-4000-8000-000000000001'
        AND l.entry_id = i.entry_id
   );

SELECT mainline.fn_ledger_cas_append(
         'dec0de00-0001-4000-8000-000000000001', i.entry_id, i.leaf_hash,
         'dec0de00-000f-4000-8000-000000000002'::UUID)
  FROM mainline.ledger_intake i
 WHERE i.entry_id = 'dec0de00-000e-4000-8000-000000000004'
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_leaf l
      WHERE l.site_code = 'dec0de00-0001-4000-8000-000000000001'
        AND l.entry_id = i.entry_id
   );

-- 8.3 · THE INTERIOR NODES — RFC 6962 §2.1, read back out of the leaves
--
-- `(level, idx)` is the RFC 6962 coordinate: level L node I covers leaves [I·2^L, (I+1)·2^L).
-- Level 1 node 0 covers leaves 0-1, level 1 node 1 covers leaves 2-3, and level 2 node 0 is the
-- root of the whole four-leaf tree. `0x01` is the INTERIOR domain separator; applying the leaf
-- prefix `0x00` a second time here is the classic way to produce a proof that verifies against
-- nothing, and `reads._mth` documents the same trap from the reader's side.

INSERT INTO mainline.ledger_node (site_code, level, idx, hash)
SELECT 'dec0de00-0001-4000-8000-000000000001', 1, 0,
       digest(decode('01', 'hex') || l0.leaf_hash || l1.leaf_hash, 'sha256')
  FROM mainline.ledger_leaf l0, mainline.ledger_leaf l1
 WHERE l0.site_code = 'dec0de00-0001-4000-8000-000000000001' AND l0.seq = 0
   AND l1.site_code = 'dec0de00-0001-4000-8000-000000000001' AND l1.seq = 1
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_node
      WHERE site_code = 'dec0de00-0001-4000-8000-000000000001' AND level = 1 AND idx = 0
   );

INSERT INTO mainline.ledger_node (site_code, level, idx, hash)
SELECT 'dec0de00-0001-4000-8000-000000000001', 1, 1,
       digest(decode('01', 'hex') || l2.leaf_hash || l3.leaf_hash, 'sha256')
  FROM mainline.ledger_leaf l2, mainline.ledger_leaf l3
 WHERE l2.site_code = 'dec0de00-0001-4000-8000-000000000001' AND l2.seq = 2
   AND l3.site_code = 'dec0de00-0001-4000-8000-000000000001' AND l3.seq = 3
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_node
      WHERE site_code = 'dec0de00-0001-4000-8000-000000000001' AND level = 1 AND idx = 1
   );

INSERT INTO mainline.ledger_node (site_code, level, idx, hash)
SELECT 'dec0de00-0001-4000-8000-000000000001', 2, 0,
       digest(decode('01', 'hex') || n0.hash || n1.hash, 'sha256')
  FROM mainline.ledger_node n0, mainline.ledger_node n1
 WHERE n0.site_code = 'dec0de00-0001-4000-8000-000000000001' AND n0.level = 1 AND n0.idx = 0
   AND n1.site_code = 'dec0de00-0001-4000-8000-000000000001' AND n1.level = 1 AND n1.idx = 1
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_node
      WHERE site_code = 'dec0de00-0001-4000-8000-000000000001' AND level = 2 AND idx = 0
   );

-- 8.4 · THE TWO CHECKPOINTS
--
-- `root_hash` is SELECTED from `mainline.ledger_node`, so the checkpoint commits to the tree the
-- appender actually built. The note `body` is the C2SP tlog-checkpoint text, and `tree_size` and
-- the root are redundant with it ON PURPOSE: a verifier parses the note and compares, and a
-- disagreement is a finding. That redundancy is only worth having when the note is BUILT from
-- the same expression the column is, which is why `encode(n.hash, 'hex')` appears twice here and
-- no hex literal appears at all.

INSERT INTO mainline.ledger_checkpoint (
  site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256, admissible, issued_at
)
SELECT
  'dec0de00-0001-4000-8000-000000000001',
  2,
  n.hash,
  'mainline/dec0de00-0001-4000-8000-000000000001' || chr(10) || '2' || chr(10)
    || encode(n.hash, 'hex') || chr(10),
  '{"synthetic": true, "drand_round": 2, "nist_pulse": 2,
    "source": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
  digest('mainline-demo/ledger/logsig/2', 'sha256'),
  digest('mainline-demo/ledger/canon-src', 'sha256'),
  true,
  TIMESTAMPTZ '2026-08-01 01:00:00+00'
FROM mainline.ledger_node n
 WHERE n.site_code = 'dec0de00-0001-4000-8000-000000000001' AND n.level = 1 AND n.idx = 0
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_checkpoint
      WHERE site_code = 'dec0de00-0001-4000-8000-000000000001' AND tree_size = 2
   );

INSERT INTO mainline.ledger_checkpoint (
  site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256, admissible, issued_at
)
SELECT
  'dec0de00-0001-4000-8000-000000000001',
  4,
  n.hash,
  'mainline/dec0de00-0001-4000-8000-000000000001' || chr(10) || '4' || chr(10)
    || encode(n.hash, 'hex') || chr(10),
  '{"synthetic": true, "drand_round": 4, "nist_pulse": 4,
    "source": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
  digest('mainline-demo/ledger/logsig/4', 'sha256'),
  digest('mainline-demo/ledger/canon-src', 'sha256'),
  true,
  TIMESTAMPTZ '2026-08-01 01:30:00+00'
FROM mainline.ledger_node n
 WHERE n.site_code = 'dec0de00-0001-4000-8000-000000000001' AND n.level = 2 AND n.idx = 0
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_checkpoint
      WHERE site_code = 'dec0de00-0001-4000-8000-000000000001' AND tree_size = 4
   );

-- 8.5 · THE WITNESS COSIGNATURES
--
-- One per checkpoint. `fn_recall_policy_anchored` requires the anchor to sit inside a checkpoint
-- that is BOTH admissible AND cosigned, so a checkpoint without its cosignature would refuse §9.

INSERT INTO mainline.cosignature (
  site_code, tree_size, witness_id, trust_domain, adverse, sig, received_at
) VALUES (
  'dec0de00-0001-4000-8000-000000000001',
  2,
  'witness.demo/hsr-1', 'union_hsr', true,
  digest('mainline-demo/ledger/cosig/2', 'sha256'),
  TIMESTAMPTZ '2026-08-01 01:05:00+00'
)
ON CONFLICT DO NOTHING;

INSERT INTO mainline.cosignature (
  site_code, tree_size, witness_id, trust_domain, adverse, sig, received_at
) VALUES (
  'dec0de00-0001-4000-8000-000000000001',
  4,
  'witness.demo/hsr-1', 'union_hsr', true,
  digest('mainline-demo/ledger/cosig/4', 'sha256'),
  TIMESTAMPTZ '2026-08-01 01:35:00+00'
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

-- ──────────────────────────────────────────────────────────────────────────────────────────────
-- 10 · THE SECOND GATED SUBJECT — a change request against the clause the incident names
--
-- WHY THIS SUBJECT IS HERE AT ALL. `apps/console/src/data/resources.ts` declares twelve navigable
-- resources and one of them is `change_request`: `GET /v1/change-requests/{cr_id}` (`:84-90`), in
-- `RESOURCE_KEYS` (`:224`), against the committed contract
-- `apps/console/contracts/change-request.schema.json`, routed by `app.py:213`, read by
-- `reads.py::read_change_request`, over the table `0051_change_request.sql` creates, with nine
-- legal transitions seeded by `0017b_subject_transition_seed.sql:38-46`. Seven layers of product
-- for a subject this file did not carry: a judge who clicked the resource got a 404, and the
-- fixture that asked for its identifier errored 63 of the demo-api suite's 444 results. The ruling
-- to ADD the subject rather than assert the 404 is `docs/leads/demo-suite-plan.md` §1.1; the
-- evidence, the row and the state are written down in `docs/decisions/demo-change-request.md`.
--
-- THIS IS AN ADDED SUBJECT, NOT A RESHAPED VALUE, AND THE DIFFERENCE IS CHECKABLE. Every
-- identifier below is a fresh literal in the `dec0de00-…` family this file already uses, chosen to
-- equal nothing in the codebase; `grep` for any of them under `apps/demo-api/src/` finds nothing.
-- The test fixture READS them back out of the database with a query, exactly as it does the
-- permit's. Nothing here was moved to make a test agree with a constant — that is the act three
-- negative controls caught once already, and it stays caught.
--
-- WHAT IT SAYS. The permit is one ref of the protected branch; this is a proposed edit to the
-- branch itself. It proposes to EDIT the very clause version §4 seeded — `DEMO-SOP-0001 §7.3.2(b)`
-- — which is the clause the 2019 precursor of §5 reaches, so the closure of §6 arms an obligation
-- against the change request exactly as it does against the permit. It therefore stands in
-- `checks_materialised` with ONE open blocking obligation nobody has disposed of. `draft` would
-- have been one INSERT and would have demonstrated no gate at all.
--
-- WHAT IS PROJECTED AND WHAT IS SUPPLIED — MEASURED ON THIS SCHEMA, NOT ASSUMED.
--
--   * `open_blocking`, `open_residue` and `open_conflicts` are NOT supplied. `fn_check_materialised`
--     (0101, welded to `blocking_check` by 0121) takes `FOR UPDATE` on the change request and
--     raises `open_blocking` and `gate_epoch` when the obligation below is inserted — the same
--     trigger, on the same path, as the permit's. After this file they read 1 / 0 / 0, epoch 1.
--   * `severity`, `virulence` and `closure_gen` on the obligation are supplied as 0 / 'routine' / 0
--     and are OVERWRITTEN by `fn_check_project` (0100, welded by 0120) from
--     `mainline.clause_blame_current` (MI25). They read back 4 / `blood_major` / 0.
--   * `site_role` IS supplied, and that is the schema's doing rather than a shortcut.
--     `0109_fn_site_role.sql` ships "DELIBERATELY UNWELDED IN THIS BAND" — the kernel's acyclicity
--     ruling reserves a gated subject's trigger slot for the merge gate — and no migration welds it
--     to `mainline.permit` or to `mainline.change_request`. The column is `NAME NOT NULL` with no
--     default, so omitting it is `23502`, not a projection. `demo_permit.sql` §1 supplies it for
--     the permit for the same reason. The value is `mainline.site.site_role`, which is the
--     authority the unwelded function would have read.
-- ──────────────────────────────────────────────────────────────────────────────────────────────

INSERT INTO mainline.change_request (
  cr_id, site_id, site_role, external_ref, ref_name, target_ref, opened_at
) VALUES (
  'dec0de00-000c-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',   -- the site §1 opened; no second site is invented
  'demo_site',
  'DEMO-MOC-0001',                          -- the customer's management-of-change identifier
  'refs/changes/demo-0001',
  'refs/heads/main',                        -- the protected branch the commit DAG of §3 is on
  TIMESTAMPTZ '2026-08-01 03:00:00+00'
)
ON CONFLICT DO NOTHING;

-- WHAT THE CHANGE REQUEST PROPOSES. `relation` is drawn from `cr_clause_relation_known`
-- ('edits' | 'introduces' | 'retires'), and `fk_cr_clause_version` names the exact
-- (clause_uuid, commit_id) pair §4 wrote — so "this change request is about that clause version"
-- is a foreign key rather than a sentence in a comment.
INSERT INTO mainline.cr_clause (cr_id, clause_uuid, commit_id, relation)
VALUES (
  'dec0de00-000c-4000-8000-000000000001',
  'dec0de00-0004-4000-8000-000000000001',
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  'edits'
)
ON CONFLICT DO NOTHING;

-- THE OBLIGATION, AND THE ONE COLUMN THAT MUST STAY NULL.
-- `mainline.blocking_check` is subject-polymorphic over the two gated subjects, and
-- `CONSTRAINT exactly_one_subject CHECK ((permit_id IS NULL) <> (cr_id IS NULL))` (0058) is what
-- stops one obligation being counted twice and cleared once. So `permit_id` is ABSENT here and
-- `cr_id` carries the subject. That is also what keeps the permit's own obligation a single row:
-- every reader in the demo API and in the test fixture asks
-- `FROM mainline.blocking_check WHERE permit_id = …`, and a CR obligation that also named the
-- permit would make each of those queries return two.
INSERT INTO mainline.blocking_check (
  check_id, subject_kind, cr_id, site_id, clause_uuid, commit_id, precursor_event_id,
  origin, severity, virulence, closure_gen, evidence_summary, materialised_at
) VALUES (
  'dec0de00-000d-4000-8000-000000000001',
  'change_request',
  'dec0de00-000c-4000-8000-000000000001',
  'dec0de00-0001-4000-8000-000000000001',
  'dec0de00-0004-4000-8000-000000000001',
  digest('mainline-demo/commit/clause-v1', 'sha256'),
  'dec0de00-0005-4000-8000-000000000001',
  'blame_ancestry',
  0, 'routine', 0,                       -- projected over by fn_check_project (MI25)
  'SYNTHETIC — recalled precursor DEMO-INC-0001 reaches the clause version this change request '
  'proposes to edit, so the same closure that armed the permit''s obligation arms this one.',
  TIMESTAMPTZ '2026-08-01 03:00:10+00'
)
ON CONFLICT DO NOTHING;

-- THE DEFEATER VOCABULARY FOR THIS OBLIGATION, for the same reason `demo_permit.sql` §3b carries
-- one: `defeaters.resolve_defeater_vocabulary` refuses a check that offers nothing, because a
-- disposition pins the digest of the set the signer was SHOWN and there is no constant to fall
-- back to. Seeding only the permit's vocabulary would leave the second gated subject signable in
-- principle and unsignable in fact — the same defect, one subject over, which is the shape this
-- repository keeps rediscovering.
--
-- THE CODES ARE NOT COPIED FROM THE PERMIT'S, AND THAT IS 0064 WORKING RATHER THAN AN
-- INCONSISTENCY. `PRIMARY KEY (check_id, defeater_code)`: a code is unique WITHIN a check and
-- meaningless outside it, because the prompt beside it is what gives it meaning. The permit's
-- obligation asks whether stored energy was isolated before intrusive work — a question about a
-- JOB. This one is about a proposed EDIT to the clause that carries that requirement, so the
-- honest defeaters are about the edit: whether it preserves the control the precursor's blame
-- reaches, whether the anchor it touches is the one under blame, and whether the precursor's
-- finding was already answered by a different control. Reusing `WORK_NOT_INTRUSIVE` here would be
-- a code that reads plausibly and means nothing, which is worse than an absent row because it
-- survives review.
--
-- The digest is aggregated from these rows, never written down — see `demo_permit.sql` §3b for
-- why a literal here would be a constant that merely looks like a hash.

WITH options (defeater_code, prompt) AS (
  VALUES
    ('CONTROL_PRESERVED_BY_EDIT',
     'Which control from the precursor''s corrective set does the proposed text still require, and where in it?'),
    ('EDIT_OUTSIDE_BLAMED_ANCHOR',
     'Which anchor does this edit touch, and why is it not the one the precursor''s blame reaches?'),
    ('PRECURSOR_ANSWERED_ELSEWHERE',
     'Which other clause version already carries the control DEMO-INC-0001 called for, and at which commit?')
),
vocab AS (
  SELECT digest(
           string_agg(defeater_code || chr(31) || prompt, chr(30) ORDER BY defeater_code),
           'sha256'
         ) AS sha
    FROM options
)
INSERT INTO mainline.defeater_option (check_id, defeater_code, prompt, vocab_sha256)
SELECT
  'dec0de00-000d-4000-8000-000000000001',
  o.defeater_code,
  o.prompt,
  v.sha
  FROM options AS o CROSS JOIN vocab AS v
ON CONFLICT DO NOTHING;

-- THE CLIENT'S CLAIM, ON THE CHANGE REQUEST'S OWN HASH CHAIN: `draft` → `checks_materialised`.
-- `cr_legal_edge` is a foreign key onto `mainline.subject_transition`, so an illegal transition
-- here is not refused by a rule — it is NOT REPRESENTABLE. `chain_digest` is a STORED generated
-- column and cannot be supplied.
--
-- `WHERE NOT EXISTS` rather than `ON CONFLICT DO NOTHING`, for the reason stated above
-- `clause_version`: `fn_cr_event_chain` (0106) is a BEFORE INSERT trigger that can raise, and a
-- BEFORE trigger runs BEFORE conflict resolution, so `ON CONFLICT` cannot suppress an exception it
-- has already raised. This is the genesis row (`seq = 1`, `prev_seq = 0`), which that function
-- exempts from the predecessor lookup only while the chain is empty — a second offer of it would
-- fall through to the lookup and be refused. The seed must therefore not offer the row at all.
INSERT INTO mainline.cr_event (
  cr_id, seq, prev_seq, from_state, to_state, subject_kind, actor_sub, payload, prev_digest, at
)
SELECT
  'dec0de00-000c-4000-8000-000000000001',
  1, 0, 'draft', 'checks_materialised', 'change_request', 'demo.signer',
  '{"synthetic": true, "to": "checks_materialised",
    "source": "verticals/mainline/db/seeds/demo/demo_world.sql"}'::JSONB,
  '\x0000000000000000000000000000000000000000000000000000000000000000'::BYTES,
  TIMESTAMPTZ '2026-08-01 03:00:20+00'
WHERE NOT EXISTS (
  SELECT 1 FROM mainline.cr_event
   WHERE cr_id = 'dec0de00-000c-4000-8000-000000000001' AND seq = 1
);

-- MOVE THE HEAD, exactly as `demo_permit.sql` §6 does for the permit: the event log is the record
-- and `state`/`head_seq` are its projection, written last and written to match the chain, so a
-- reader who does not trust the columns can recompute them from `mainline.cr_event`.
-- `open_blocking` and `gate_epoch` are deliberately ABSENT from this UPDATE — the trigger owns
-- them — and `head_seq < 1` is what makes a second run change nothing. This UPDATE fires neither
-- `cr_merge_gate` (0131) nor `z_cbm_gate_cr` (0145d): both carry `WHEN NEW.state = 'merged'`.
UPDATE mainline.change_request
   SET state = 'checks_materialised', head_seq = 1
 WHERE cr_id = 'dec0de00-000c-4000-8000-000000000001'
   AND head_seq < 1;

-- ══════════════════════════════════════════════════════════════════════════════════════════════
-- END OF THE STATIC CORPUS.
--
-- What exists after this file: one site, two people with credentials, a two-commit DAG, one
-- document, one clause and its version, one severity-4 precursor, the blame edge and closure that
-- bind the two, a balanced blame account, a cosigned custody checkpoint, and the anchored recall
-- policy. None of that is gated and none of it refuses anything — that part is the *history*.
--
-- And, since §10, ONE GATED SUBJECT: the change request, in `checks_materialised`, carrying one
-- open blocking obligation nobody has disposed of.
--
-- `demo_permit.sql` adds the other one: a permit that relies on that clause version, and one open
-- obligation nobody has disposed of. Two gated subjects over one repository, which is the sentence
-- the console makes about the resource — *"the repository is the protected branch; the permit is
-- one of its refs"* — and now the sentence the data makes too.
-- ══════════════════════════════════════════════════════════════════════════════════════════════
