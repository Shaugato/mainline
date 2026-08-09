-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0066_disposition.sql
-- CREATE TABLE trappoint_ref.disposition — the product, and the exhibit
--
-- MI: MI11, MI12, MI27, MI28, MI29
-- I: I09, I10
-- COUNSEL-GATED: yes
-- RATIONALE: Two composite foreign keys carry the whole claim: (virulence, kind) into the
--            versioned clearance lattice, so a verdict that does not exist at that
--            ancestral severity is 23503 naming fk_clearance for every writer including a
--            DBA; and (receipt_id, check_id) into the exposure line, so a signature can
--            only exist against an obligation the substrate actually rendered to that
--            actor. Virulence is projected from the blame closure rather than supplied,
--            which is what stops the first key being routed around by claiming a lower
--            severity.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0066_disposition.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- @projects disposition.req_compensating, disposition.req_second_signer, disposition.req_foreign_org, disposition.req_predicate, disposition.req_reassert, disposition.min_signer_rank
-- @authority trappoint_ref.clearance_legal (virulence, kind) <= NEW (virulence, kind)
-- @on_missing raise
--
-- @projects disposition.signer_rank, disposition.signer_org, disposition.competency_sha256
-- @authority trappoint_ref.person (signer_sub) <= NEW (signer_sub)
-- @on_missing raise
--
-- SUBJECT-POLYMORPHIC UNDER RULING D2, over the 2 gated subject(s) declared:
--   permit -> trappoint_ref.permit (permit_id)
--   change_request -> trappoint_ref.change_request (cr_id)
--
-- §5.5 gives this table `permit_id UUID NOT NULL`, and that line predates finding S16.
-- Read literally it means a change request which trips `weaken_over_blood` can never be
-- dispositioned, so MI30 — "a change_request merges only with zero open blocking
-- checks" — would be satisfiable only by never opening one. The repository would be a
-- brick wall rather than a protected branch, which is the opposite of the claim. D2
-- makes the table polymorphic exactly as `blocking_check` is, and all three columns are
-- written by `fn_disposition_project` from the blocking check the disposition names —
-- never from the writer, who is not entitled to say which subject they are clearing.
--
-- ── THE SIGNATURE BLOCK ──────────────────────────────────────────────────────────────
-- signer_rank, signer_org and competency_sha256 are projections of `person` (MI27), so a
-- client that signs with signer_rank = 6 on a person whose live rank is 2 has the row
-- rewritten BEFORE `rank_floor` is evaluated and then gets 23514. That ordering is the
-- whole of case CF-19: asserting only the 23514 would pass against an implementation
-- that trusted the client and happened to have a low floor.
--
-- competency_snapshot is FROZEN AT SIGNATURE, never a join. A live join to an HR system
-- returns TODAY's competency at trial, which is useless and looks like backfilling. The
-- frozen snapshot supports a provable claim: at 02:14 on 14 March the system checked,
-- the record said this, and here is the hash of the source record. It fails closed —
-- a missing `person` row refuses the disposition with P0001 (case CF-20).
--
-- ── THE NEUTRAL MEASUREMENTS (I15 / A-RULE) ──────────────────────────────────────────
-- deliberation_seconds, evidence_opened, reading_floor_met and severity_snapshot are
-- RECORDED AND NEVER THRESHOLDED HERE. No CHECK on this table reads them. That is not
-- squeamishness: a threshold on deliberation time in the schema would be a surveillance
-- instrument with no signature on it, and ADR 0001 defaults per-approver dwell timing to
-- OFF. deliberation_seconds is derived from the SERVER-issued exposure receipt — a
-- record of what the system did, not a measurement of a worker.
--
-- evidence_opened = false before a fatality is a devastating row, and it ships anyway. A
-- system that deliberately declines to record whether the human read the warning is a
-- worse exhibit, because that design choice is itself discoverable, dated and authored.
--
-- reading_floor_met has POSITIVE polarity and it does work (finding S19): breaching the
-- floor does not raise, it projects `unmet_floor_count` onto the subject and PRICES the
-- consequence — the subject cannot complete without a countersignature from a second,
-- differently-credentialed signer. Fast stays legal; it just names a second person.
--
-- ── max_ttl_hours IS NULLABLE, AND THAT IS DELIBERATE ────────────────────────────────
-- It is a projection of `clearance_legal.max_ttl_hours`, which is itself nullable: NULL
-- means the verdict does not expire, and twelve of the twenty-one seeded cells are NULL.
-- Making this column NOT NULL would make `ttl_enforced`'s first branch dead syntax and
-- would require inventing a sentinel for "no expiry" that every reader would then have
-- to remember. It is the one projected requirement column that is not NOT NULL, and it
-- is not in the binding's `strictest` map for the same reason.
--
-- ── retracted_by IS THE SINGLE PERMITTED UPDATE IN THE OPERATIONAL ZONE ──────────────
-- A BEFORE UPDATE trigger (`fn_disposition_retract_only`, migration band 0100+) raises
-- unless the ONLY changed column is `retracted_by` and its prior value was NULL. A
-- retraction increments the subject's open counter AND bumps `gate_epoch`, so a
-- retraction after the subject merged is refused by the epoch pin with 23503 naming
-- `epoch_pin_permit` (case CF-40) — refusal by referential integrity, not by policy.
-- `retraction_not_reflexive` closes the one hole the self-reference leaves open: the
-- foreign key would happily accept a disposition that retracts itself.

CREATE TABLE trappoint_ref.disposition (
  disposition_id       UUID NOT NULL DEFAULT gen_random_uuid(),
  check_id             UUID NOT NULL REFERENCES trappoint_ref.blocking_check (check_id),
  receipt_id           UUID NOT NULL,
  -- ▼ PROJECTED by fn_disposition_project from the blocking check named above (D2).
  subject_kind         STRING NOT NULL,
  permit_id            UUID NULL REFERENCES trappoint_ref.permit (permit_id),
  cr_id                UUID NULL REFERENCES trappoint_ref.change_request (cr_id),
  site_id              UUID NOT NULL,
  -- ▲
  kind                 trappoint_ref.disposition_kind NOT NULL,
  -- ▼ PROJECTED from the blame closure via the blocking check (finding S1, MI25).
  virulence            trappoint_ref.virulence_class NOT NULL,
  closure_gen          INT8 NOT NULL,
  -- ▲
  defeater_code        STRING NOT NULL,
  defeater_vocab_sha256 BYTES NOT NULL,
  rationale            STRING NOT NULL,
  evidence_sha256      BYTES NOT NULL,
  signer_sub           STRING NOT NULL,
  -- ▼ PROJECTED from trappoint_ref.person (MI27). See the @authority banner above.
  signer_rank          INT2 NOT NULL,
  signer_org           STRING NOT NULL,
  -- ▲
  signer_credential_id BYTES NOT NULL
                         REFERENCES trappoint_ref.signing_credential (credential_id),
  countersigner_sub    STRING NULL,
  countersigner_rank   INT2 NULL,
  countersigner_org    STRING NULL,
  countersigner_credential_id BYTES NULL
                         REFERENCES trappoint_ref.signing_credential (credential_id),
  signature_alg        STRING NOT NULL,
  authenticator_data   BYTES NOT NULL,
  client_data_json     BYTES NOT NULL,
  user_verified        BOOL NOT NULL,
  signed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  competency_snapshot  JSONB NOT NULL,
  competency_source_id UUID NOT NULL,
  competency_sha256    BYTES NOT NULL,
  -- ▼ PROJECTED from trappoint_ref.clearance_legal (MI11, ruling D3: a missing row
  --   projects the STRICTEST values so that fk_clearance fires with its name attached).
  req_compensating     BOOL NOT NULL,
  req_second_signer    BOOL NOT NULL,
  req_foreign_org      BOOL NOT NULL,
  req_predicate        BOOL NOT NULL,
  req_reassert         BOOL NOT NULL,
  min_signer_rank      INT2 NOT NULL,
  max_ttl_hours        INT4 NULL,
  -- ▲
  compensating_clause_uuid UUID NULL REFERENCES trappoint_ref.clause (clause_uuid),
  predicate_id         UUID NULL,
  reassert_by          TIMESTAMPTZ NULL,
  expires_at           TIMESTAMPTZ NULL,
  verbatim_anchor_count INT4 NOT NULL DEFAULT 0,
  required_anchors     INT4 NOT NULL DEFAULT 0,
  particularity        FLOAT8 NULL,
  preimage_key         BYTES NULL,
  stale_replay         BOOL NOT NULL DEFAULT false,
  deliberation_seconds INT8 NOT NULL,
  evidence_opened      BOOL NOT NULL,
  reading_floor_met    BOOL NOT NULL DEFAULT true,
  prior_override_count INT8 NOT NULL,
  severity_snapshot    INT2 NOT NULL,
  retracted_by         UUID NULL REFERENCES trappoint_ref.disposition (disposition_id),

  -- THE EXPOSURE BINDING (MI12, case CF-18). Onto the PAIR, never onto the obligation
  -- alone: a signature against a receipt that never carried this obligation is 23503.
  CONSTRAINT fk_exposure FOREIGN KEY (receipt_id, check_id)
    REFERENCES trappoint_ref.exposure_line (receipt_id, check_id),

  -- THE CLEARANCE LATTICE (MI11, case CF-07). (blood_fatal, mechanism_absent) is not a
  -- stricter row in 0018b; it is NO row, so this key is 23503 and names itself.
  CONSTRAINT fk_clearance FOREIGN KEY (virulence, kind)
    REFERENCES trappoint_ref.clearance_legal (virulence, kind),

  CONSTRAINT substantive CHECK (length(rationale) >= 120),
  CONSTRAINT rank_floor CHECK (signer_rank >= min_signer_rank),
  CONSTRAINT uv_required CHECK (user_verified = true),
  CONSTRAINT distinct_credential CHECK (countersigner_credential_id IS NULL
    OR countersigner_credential_id <> signer_credential_id),
  CONSTRAINT needs_compensating
    CHECK (req_compensating = false OR compensating_clause_uuid IS NOT NULL),
  CONSTRAINT needs_second_signer CHECK (req_second_signer = false
    OR (countersigner_credential_id IS NOT NULL AND countersigner_sub <> signer_sub)),
  CONSTRAINT needs_foreign_org CHECK (req_foreign_org = false
    OR (countersigner_org IS NOT NULL AND countersigner_org <> signer_org)),
  CONSTRAINT needs_predicate CHECK (req_predicate = false OR predicate_id IS NOT NULL),
  CONSTRAINT needs_reassert CHECK (req_reassert = false OR reassert_by IS NOT NULL),
  -- Finding S12 / MI28: the window is BOUNDED, not merely present. `expires_at IS NOT
  -- NULL` alone would admit a verdict that expires in the year 3000.
  CONSTRAINT ttl_enforced CHECK (max_ttl_hours IS NULL
    OR (expires_at IS NOT NULL
        AND expires_at <= signed_at + (max_ttl_hours * INTERVAL '1 hour'))),
  -- Finding S8 / MI29: overrides escalate against the PERSON, across subjects, with NO
  -- ceiling. prior_override_count is projected from override_ledger, so it cannot be
  -- supplied; and there is deliberately no upper bound on the required rank, because a
  -- ceiling is the rung at which the ladder stops meaning anything.
  CONSTRAINT override_escalates CHECK (kind <> 'emergency_override'
    OR (expires_at IS NOT NULL AND countersigner_credential_id IS NOT NULL
        AND signer_rank >= 3 + prior_override_count)),
  -- Authority to waive derives from a FROZEN credential and fails closed.
  CONSTRAINT waiver_authority CHECK (virulence NOT IN ('blood_major', 'blood_fatal')
    OR competency_snapshot->'authorisations' ? 'ISOLATION_AUTHORITY'),
  -- Gist may accuse; only verbatim may acquit.
  CONSTRAINT verbatim_floor
    CHECK (kind NOT IN ('mechanism_absent', 'mitigated')
           OR verbatim_anchor_count >= required_anchors),

  CONSTRAINT disposition_subject_kind_known
    CHECK (subject_kind IN ('permit', 'change_request')),
  CONSTRAINT exactly_one_subject
    CHECK ((permit_id IS NULL) <> (cr_id IS NULL)),
  CONSTRAINT subject_matches
    CHECK ((subject_kind = 'permit' AND permit_id IS NOT NULL)
        OR (subject_kind = 'change_request' AND cr_id IS NOT NULL)),
  CONSTRAINT retraction_not_reflexive
    CHECK (retracted_by IS NULL OR retracted_by <> disposition_id),
  CONSTRAINT disposition_signer_sub_stated CHECK (signer_sub <> ''),
  CONSTRAINT disposition_defeater_code_stated CHECK (defeater_code <> ''),
  CONSTRAINT disposition_signature_alg_stated CHECK (signature_alg <> ''),
  CONSTRAINT disposition_authenticator_present CHECK (length(authenticator_data) > 0),
  CONSTRAINT disposition_client_data_present CHECK (length(client_data_json) > 0),
  CONSTRAINT disposition_evidence_is_sha256 CHECK (length(evidence_sha256) = 32),
  CONSTRAINT disposition_vocab_is_sha256 CHECK (length(defeater_vocab_sha256) = 32),
  CONSTRAINT disposition_competency_is_sha256 CHECK (length(competency_sha256) = 32),
  CONSTRAINT disposition_rank_range CHECK (signer_rank BETWEEN 1 AND 9),
  CONSTRAINT disposition_min_rank_range CHECK (min_signer_rank BETWEEN 1 AND 9),
  CONSTRAINT disposition_severity_range CHECK (severity_snapshot BETWEEN 0 AND 5),
  CONSTRAINT disposition_deliberation_nonneg CHECK (deliberation_seconds >= 0),
  CONSTRAINT disposition_prior_override_nonneg CHECK (prior_override_count >= 0),
  CONSTRAINT disposition_anchor_counts_nonneg
    CHECK (verbatim_anchor_count >= 0 AND required_anchors >= 0),
  CONSTRAINT pk_disposition PRIMARY KEY (disposition_id)
);
