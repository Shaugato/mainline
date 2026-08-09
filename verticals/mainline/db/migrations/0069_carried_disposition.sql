-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0069_carried_disposition.sql
-- CREATE TABLE mainline.carried_disposition — one signature, many permits, bounded and revocable
--
-- MI: MI28, MI11, MI08
-- I: I12, I10
-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
-- RATIONALE: Most noise is REPETITION, not wrongness — the same precursor firing on the fortieth materially identical permit. A carried disposition lets later permits reference an existing signature instead of manufacturing a fresh one, so volume falls by the repetition factor without hiding a single recall. What makes that safe rather than convenient is that the reuse is bounded (S12/MI28), typed against the clearance lattice by composite foreign key (MI11), and automatically revoked by any new commit in the blame ancestry of the covered clauses, any new bonded event at severity >= 4, expiry, or any control_delta='weaken' in scope.
--
-- migration:  0069_carried_disposition
-- band:       0069-0070z · datamodel/ex-dm-disposition · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). `disposition`,
--             `disposition_citation` and `override_ledger` are SUBSTRATE under MR-1's object
--             test and are RENDERED at 0066-0068z; the carried pair is VERTICAL — a second
--             TRAPPOINT vertical may have no repetition problem at all — so it is authored here.
-- statements: 1
-- source:     ARCHITECTURE.md §5.5 "Carried dispositions with ancestry revocation (S18 rename)"
--             (shape, with three additions argued below) · findings S12, S18 · §16 MI28, MI11 ·
--             BUILD_PLAN.md §2.1 (what the counsel gate blocks) · docs/leads/datamodel.md DM-17
-- requires:   0018a mainline.clearance_legal (RENDERED) + 0018b its seed · 0022
--             mainline.signing_credential (RENDERED) · 0024 mainline.commit_obj · 0032
--             mainline.activity_node · 0033 mainline.event
-- projects:   signer_rank <= mainline.person; min_signer_rank, lattice_max_ttl_hours <=
--             mainline.clearance_legal (virulence, kind). Both banners below; both RAISE on a
--             missing source. The trigger is band 0140-0149z and DOES NOT EXIST YET.
-- sqlstate:   23503 on fk_carried_clearance / fk_carried_event / fk_carried_scope /
--             fk_signer_credential / fk_anchor_commit; 23514 on carried_bounded /
--             carried_substantive / carried_rank_floor / ttl_within_lattice / max_ttl_positive /
--             revocation_reasoned; 23505 on the pk
-- exhibits:   spec R-3 (Exhibit Uniqueness) requires a refusal-bearing name to be unique across
--             the WHOLE schema. `mainline.disposition` (0066) already owns `substantive`,
--             `rank_floor` and `fk_clearance`, and `mainline.event_severity_revision` (0036) owns
--             `substantive` too, so the mirrored names here are `carried_substantive`,
--             `carried_bounded`, `carried_rank_floor` and `fk_carried_clearance`. The first two
--             are named by the spec itself (spec/CHANGELOG.md R-3) and `carried_bounded` is
--             asserted by string in spec/conformance/manifest.toml case CF-66.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- COUNSEL GATE G0 — WHAT SHIPS AND WHAT IS CONFIGURATION (DM-17).
--
-- The DDL below ships UNCONDITIONALLY. It is not forked per legal answer, because a DDL fork per
-- legal answer is two schemas to test and one to get wrong. What is switchable is CONFIGURATION
-- and it lives in `verticals/mainline/db/ext/disposition_ext/` — the conservative reading, in
-- plain words, plus the three keys `mechanism_absent_over_fatal_ancestry`, `record_evidence_
-- opened` and `silence_ledger_zone`. THAT DIRECTORY DOES NOT EXIST ON THIS TREE. It was a
-- deliverable of the dissolved `dm-disposition` worker and the reconciliation of 2026-08-08 did
-- not reassign it. This file does not create it — a worker that writes outside its allocation is
-- how the incident of 2026-08-08 started — and the gap is reported rather than quietly filled.
--
-- The CONSERVATIVE default is already load-bearing here and needs no switch to be true: the three
-- cells the lattice deliberately leaves empty — (blood_fatal, mechanism_absent), (blood_fatal,
-- accept_residual), (blood_major, accept_residual) — are absent from 0018b, so `fk_carried_clearance`
-- below refuses those carried dispositions with 23503 naming itself, for every writer, including
-- a DBA and including the MCP insert path. If counsel opens a cell, that is a seed change with an
-- approver's name on it and this file does not move.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- @projects   carried_disposition.signer_rank
-- @authority  mainline.person (signer_sub) <= NEW (signer_sub)
-- @on_missing raise
--
-- @projects   carried_disposition.min_signer_rank, carried_disposition.lattice_max_ttl_hours
-- @authority  mainline.clearance_legal (virulence, kind) <= NEW (virulence, kind)
-- @on_missing raise
--
-- ── ADDITION 1 TO §5.5 · `carried_rank_floor`, OVER TWO PROJECTED COLUMNS ────────────────────
-- §5.5 gives this table a signer and a credential but no rank, so as written a rank-1 signer can
-- issue a blood_major carried disposition that a rank-1 signer could not issue as a single
-- `disposition` (0066 carries `rank_floor` over the same two projections). That asymmetry runs in
-- precisely the wrong direction: THE THING THAT REPEATS FORTY TIMES MUST NOT BE HELD TO A LOWER
-- BAR THAN THE THING THAT HAPPENS ONCE. `signer_rank` is projected from `mainline.person` and
-- `min_signer_rank` from the same `clearance_legal` row `fk_carried_clearance` points at, so this
-- adds no new authority and no new failure mode — only the comparison that was missing.
--
-- ── ADDITION 2 TO §5.5 · `ttl_within_lattice`, OVER A THIRD PROJECTED COLUMN ──────────────────
-- `carried_bounded` (S12) forces `expires_at <= issued_at + max_ttl_hours`, but `max_ttl_hours` is
-- supplied by the signer, so it bounds the window against a number the signer chose. The lattice
-- has its OWN ceiling per cell (`clearance_legal.max_ttl_hours`, e.g. 12 hours for an emergency
-- override at blood_major), and nothing in §5.5 compares the two. `lattice_max_ttl_hours` is
-- projected from the lattice and `ttl_within_lattice` refuses a carried window longer than the
-- cell permits. NULL there means the cell does not expire, which the constraint admits — the
-- lattice's silence is not a licence this file invents a number for.
--
-- ── ADDITION 3 TO §5.5 · `max_ttl_positive`, `revocation_reasoned`, `revoked_after_issue` ─────
-- Hygiene, each closing a state that is representable in §5.5's shape and means nothing:
-- `max_ttl_hours = 0` (a window of zero length that `carried_bounded` would then make unsatisfiable in a
-- confusing way), a `revoked_at` with no reason or a reason with no `revoked_at` (a revocation
-- nobody can explain, or an explanation of a revocation that did not happen), and a revocation
-- timestamped before the signature it revokes.
--
-- ── WHAT THIS TABLE DOES *NOT* ENFORCE, STATED SO NOBODY HAS TO DISCOVER IT ───────────────────
-- `clearance_legal` carries five requirement flags. This file enforces the rank floor and the TTL
-- ceiling. It does NOT enforce `req_second_signer`, `req_foreign_org`, `req_predicate` or
-- `req_reassert`, because §5.5 gives this table no countersigner, no signer org, no predicate
-- pointer and no reassert deadline, and inventing four columns and their projections here would
-- be re-deriving `disposition` (0066) under a second name — which is exactly the divergence MR-1
-- exists to prevent. The compensating control is that a carried disposition CLEARS NOTHING BY
-- ITSELF: it is only ever consumed through `carried_disposition_use` (0070), every consumption is
-- an evidenced row, and that row carries the coverage and liveness refusals. A carried
-- disposition whose cell requires a second signer is therefore recorded, reusable, and still
-- short of what the lattice demands — a gap for the G0 counsel answer to close by policy, and one
-- this file names rather than hides.
--
-- ── `virulence` IS THE SIGNER'S DECLARED COVERAGE CEILING, AND MISDECLARING IT IS SELF-PUNISHING
-- On `disposition` (0066) virulence is projected from the blame closure via a specific blocking
-- check. A carried disposition has no check — that is the entire point of it — so there is
-- nothing to project from and the signer states the band they are willing to cover. Both errors
-- are handled without a trigger. UNDERSTATING shrinks coverage: `carried_covers_check` in 0070
-- refuses any use against a check of higher virulence, so a signer who writes 'routine' to duck
-- the lattice has bought a signature that clears routine checks and nothing else. OVERSTATING
-- costs: it moves the row to a stricter lattice cell, raising `min_signer_rank` and, at the top,
-- hitting a cell that does not exist at all. The safe direction is the cheap one.
--
-- ── `max_ttl_hours` IS NOT NULL HERE THOUGH THE LATTICE ALLOWS NULL, AND THAT IS DELIBERATE ───
-- `clearance_legal.max_ttl_hours IS NULL` means "this verdict does not expire", which is a
-- defensible thing to say about ONE act on ONE check. It is not a defensible thing to say about a
-- signature that will be reused on permits nobody has opened yet, by crews nobody has hired yet,
-- against a plant that will not be the same plant. Repetition demands a clock even where a single
-- act does not. §5.5 already types this column NOT NULL; this note is why it must stay that way.
--
-- ── REVOCATION IS THE ONLY LEGAL UPDATE, AND ITS GUARD IS NOT HERE YET ────────────────────────
-- `revoked_at` and `revoke_reason` are the only columns that ever change after insert, exactly as
-- `disposition.retracted_by` is on 0066. The BEFORE UPDATE trigger that refuses every other column
-- change, and refuses un-revoking, is band 0140-0149z (dm-functions-triggers) and DOES NOT EXIST
-- YET. UNTIL IT LANDS, ANY WRITER WITH THE GRANT CAN AMEND THIS ROW. The test suite carries that
-- as a deliberately RED assertion rather than as an assumption (PL-2).
--
-- ── `anchor_commit` IS WHAT MAKES ANCESTRY REVOCATION COMPUTABLE ──────────────────────────────
-- The carried disposition is anchored to a commit, so "any NEW commit in the blame ancestry of
-- the covered clauses" is a question with a definite answer: new relative to this commit. Without
-- the anchor, "new" would mean "since I last looked", which is not a property of the data.
--
-- VERIFIED 2026-08-10 against CockroachDB CCL v26.2.5 (local single node, insecure, 26257). The
-- statement applies and every refusal fires by name:
--
--   * (blood_fatal, mechanism_absent) — a cell 0018b deliberately leaves empty — is refused with
--     SQLSTATE 23503 and the server names `fk_carried_clearance` (MI11);
--   * a rationale shorter than 120 characters is refused naming `carried_substantive`;
--   * `expires_at` 48 hours out against `max_ttl_hours = 4` is refused naming `carried_bounded` (MI28);
--   * `max_ttl_hours = 48` against a lattice ceiling of 12 is refused naming `ttl_within_lattice`
--     (addition 2);
--   * `signer_rank = 1` against `min_signer_rank = 4` is refused naming `carried_rank_floor` (addition 1);
--   * setting `revoked_at` with no `revoke_reason` is refused naming `revocation_reasoned`.
--
-- Evidence: tests/integration/schema/test_mi_boundary_override.py, the carried-disposition cases.

CREATE TABLE mainline.carried_disposition (
  carried_id           UUID   NOT NULL DEFAULT gen_random_uuid(),
  site_id              UUID   NOT NULL,   -- authoritative source: mainline.site (DM-3); no FK
  event_id             UUID   NOT NULL,   -- the precursor this signature answers
  scope_id             UUID   NOT NULL,   -- the activity node the coverage is bounded to
  control_class        STRING NOT NULL,
  kind                 mainline.disposition_kind NOT NULL,
  -- The signer's DECLARED coverage ceiling, not a projection. Understating shrinks coverage;
  -- overstating raises the lattice bar. See the header.
  virulence            mainline.virulence_class NOT NULL,
  rationale            STRING NOT NULL,
  signer_sub           STRING NOT NULL,
  -- ▼ PROJECTED from mainline.person (MI27-shaped). See the @authority banner above.
  signer_rank          INT2   NOT NULL,
  -- ▲
  signer_credential_id BYTES  NOT NULL,
  issued_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  max_ttl_hours        INT4   NOT NULL,   -- NOT NULL even where the lattice allows NULL
  expires_at           TIMESTAMPTZ NOT NULL,
  -- ▼ PROJECTED from mainline.clearance_legal (virulence, kind) — the same row that
  --   fk_carried_clearance points at. A missing row projects the STRICTEST values, so the
  --   foreign key fires by name rather than the projection defaulting to something permissive.
  min_signer_rank      INT2   NOT NULL,
  lattice_max_ttl_hours INT4  NULL,       -- NULL = the cell does not expire; see the header
  -- ▲
  anchor_commit        BYTES  NOT NULL,
  revoked_at           TIMESTAMPTZ NULL,
  revoke_reason        STRING NULL,
  CONSTRAINT carried_disposition_pk PRIMARY KEY (carried_id),

  -- THE CLEARANCE LATTICE (MI11). (blood_fatal, mechanism_absent) is not a stricter row in
  -- 0018b; it is NO row, so this key is 23503 and it names itself.
  CONSTRAINT fk_carried_clearance FOREIGN KEY (virulence, kind)
    REFERENCES mainline.clearance_legal (virulence, kind)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_carried_event FOREIGN KEY (event_id)
    REFERENCES mainline.event (event_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_carried_scope FOREIGN KEY (scope_id)
    REFERENCES mainline.activity_node (scope_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_signer_credential FOREIGN KEY (signer_credential_id)
    REFERENCES mainline.signing_credential (credential_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_anchor_commit FOREIGN KEY (anchor_commit)
    REFERENCES mainline.commit_obj (commit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,

  CONSTRAINT carried_substantive CHECK (length(rationale) >= 120),
  -- S12 / MI28: bounded, not merely present.
  CONSTRAINT carried_bounded CHECK (expires_at > issued_at
                            AND expires_at <= issued_at + (max_ttl_hours * INTERVAL '1 hour')),
  CONSTRAINT max_ttl_positive CHECK (max_ttl_hours > 0),
  -- Addition 2: the signer's window may not outlast the lattice's ceiling for the cell.
  CONSTRAINT ttl_within_lattice
    CHECK (lattice_max_ttl_hours IS NULL OR max_ttl_hours <= lattice_max_ttl_hours),
  -- Addition 1: what repeats forty times is held to the bar of what happens once.
  CONSTRAINT carried_rank_floor CHECK (signer_rank >= min_signer_rank),
  CONSTRAINT carried_rank_range CHECK (signer_rank BETWEEN 1 AND 9),
  CONSTRAINT carried_min_rank_range CHECK (min_signer_rank BETWEEN 1 AND 9),
  CONSTRAINT carried_control_class_stated CHECK (control_class <> ''),
  CONSTRAINT carried_signer_sub_stated CHECK (signer_sub <> ''),
  CONSTRAINT carried_anchor_is_sha256 CHECK (length(anchor_commit) = 32),
  CONSTRAINT revocation_reasoned CHECK ((revoked_at IS NULL) = (revoke_reason IS NULL)),
  CONSTRAINT revoke_reason_stated CHECK (revoke_reason IS NULL OR revoke_reason <> ''),
  CONSTRAINT revoked_after_issue CHECK (revoked_at IS NULL OR revoked_at >= issued_at),
  -- The reuse lookup: "is there a live carried disposition for this control class in this scope".
  -- Declared inline per DM-6; this is the read path the whole repetition-factor claim depends on.
  INDEX by_scope (site_id, scope_id, control_class, expires_at)
);
