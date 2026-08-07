-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI03, MI01
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: CONSERVATION OF BLAME MASS — this is the table that makes adversarial paraphrase useless, because a matcher failure is not a missed match but an undispositioned residue row, and MI03 refuses the merge while one exists; rewording changes WHICH gate you fail, never WHETHER you fail.
--
-- migration:  0049_identity_residue
-- band:       0024-0031, 0047-0049 · dm-spine
-- statements: 1
-- source:     ARCHITECTURE.md §5.3 (verbatim shape; constraints named per DM-10, partial index
--             inline per DM-6) · §16 MI03 · docs/leads/datamodel.md DM-9
-- requires:   0024 mainline.commit_obj · 0028 mainline.clause
-- projects:   max_ancestral_severity ← the blame closure, read ONLY through
--             mainline.clause_blame_current (DM-9: that view is the sole read path; a CI grep
--             fails any file in this band naming the closure table directly). Owed to
--             TRIGGER-MAP.yaml and to `fn_residue_project` in band 0130-0199, which must RAISE
--             P0001 when the closure has no row for `ancestor_clause_uuid`.
-- sqlstate:   23503 on fk_commit / fk_ancestor_clause; 23514 on reason_closed / severity_range /
--             match_score_bounded; 23505 on residue_unique
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY ADVERSARIAL PARAPHRASE DOES NOT DEFEAT MAINLINE.
--
-- The system never asks "does this text match an old clause?" — a question whose failure mode is
-- silence. It asserts a CONSERVATION LAW: every ancestor clause carrying a blame edge to a
-- severity ≥ 4 event is, in commit c, one of exactly three things —
--
--     (a) MATCHED to a clause in c;
--     (b) matched THROUGH A RECORDED SPLIT OR MERGE;
--     (c) EXPLICITLY ABSENT, with a signed disposition.
--
-- There is no fourth state. This table holds the (c)-candidates: every ancestor the matcher could
-- not place. A row with `disposition_id IS NULL` is a live claim that a blood-written obligation
-- has gone missing from this commit, and MI03 — `identity_conserved_when_issued` on
-- mainline.permit, band 0050-0065 — refuses the merge while one exists.
--
-- THE CONSEQUENCE IS THE POINT. A successful evasion of the matcher does not produce a silent
-- pass. It produces an ORPHANED BLOOD-WRITTEN OBLIGATION, which presents as deletion of a control
-- written by a fatality — and that raises a STRONGER gate than the weakening it was trying to
-- sneak past, because `mechanism_absent` and `accept_residual` do not exist as legal verdicts
-- over blood_fatal ancestry (the three deliberately absent cells of mainline.clearance_legal).
-- Matcher recall failures therefore convert into gate FALSE POSITIVES, which are adjudicable by a
-- human in minutes, instead of gate FALSE NEGATIVES, which are fatal and silent. That trade is
-- the entire justification for building an identity matcher at all: not because it is accurate,
-- but because its inaccuracies fail in the safe direction BY CONSTRUCTION.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- THE FIVE REASONS ARE A CLOSED SET, AND EACH ONE NAMES A DIFFERENT KIND OF DOUBT:
--   'unmatched'            no candidate cleared the threshold. The ancestor simply is not there.
--   'ambiguous'            two or more candidates cleared it and none dominated. Picking one
--                          would be the system guessing about an obligation's identity.
--   'anchor_drop'          a candidate matched on text but LOST AN ANCHOR — a tag, a setpoint, a
--                          CAS number, a named role. The sentence survived; the specific thing it
--                          bound to did not. This is the paraphrase attack's most common
--                          signature and the reason anchors are indexed separately (0029).
--   'opaque_control'       the clause could not be canonicalised into a Control Assertion Tuple
--                          at all, so no comparison was possible. Silence from the extractor is
--                          recorded as doubt, never as absence.
--   'citation_unresolved'  the clause cites another clause that could not be resolved in this
--                          commit, so its meaning is not fully determined.
--
-- `max_ancestral_severity` IS A PROJECTION AND IT DECIDES HOW HARD THIS ROW BITES. It is the
-- ancestral severity of the ancestor clause, read from the blame closure through
-- mainline.clause_blame_current — never computed here, never supplied by the writer. A residue
-- row over routine ancestry is a housekeeping item; a residue row over a fatality is the loudest
-- refusal the system can produce. A writer who could set this column could choose which of those
-- their own missing control was. Until band 0130-0199 lands it is client-supplied, and this file
-- says so rather than implying a control that does not exist yet.
--
-- DM-9 IN PRACTICE: this file names `mainline.clause_blame_current` and never the closure table
-- underneath it. `max(closure_gen)` discipline has to be structural — one forgotten call site
-- silently reads a superseded generation of the blame closure, and a superseded generation is a
-- LOWER severity, which is a gate that opens. The grep that enforces it (scripts/
-- grep_closure_readpath.py, owned by dm-blame) reads comments as well as code, which is why the
-- rule is honoured in the prose here too.
--
-- `residue_unique (commit_id, ancestor_clause_uuid, reason)` MAKES RE-RUNNING THE MATCHER SAFE.
-- The matcher is idempotent by construction: running it twice over the same commit produces the
-- same findings, and the second run's inserts collide on 23505 rather than doubling the count of
-- open residue. `residue_id` remains the primary key because a disposition points at ONE residue
-- row and a stable single-column identifier is what that pointer needs.
--
-- ONE ANCESTOR CAN PRODUCE SEVERAL ROWS — `reason` IS IN THE UNIQUE KEY. A clause can be both
-- 'ambiguous' and 'anchor_drop'; collapsing those into one row would force the matcher to rank
-- its own doubts and discard the rest, and the discarded one is the one that mattered. Each doubt
-- is dispositioned on its own terms.
--
-- `disposition_id` CARRIES NO FOREIGN KEY, AND THAT IS AN ORDERING FACT, NOT AN OVERSIGHT.
-- mainline.disposition is migration 0066 — in the counsel-gated band (G0) — and a forward
-- reference from 0049 to 0066 would make this file unappliable on a fresh cluster. The FK is
-- added by band 0200-0279 along with the other deferred cycle constraints. Recorded here so the
-- gap is a known one.
--
-- `ir_open (site_id, commit_id) WHERE disposition_id IS NULL` IS THE GATE'S OWN INDEX. The merge
-- gate asks exactly one question of this table — "does this commit have any undispositioned
-- residue" — on the latency-critical path, and a partial index keyed on that predicate answers it
-- with a seek. The index is PARTIAL because dispositioned residue is history: it is read by the
-- console and by disclosure, never by the gate.
--
-- `features JSONB` IS THE ARITHMETIC, KEPT. Shingle overlap, anchor Jaccard, embedding distance,
-- which bands hit — the actual numbers the matcher used, so a disputed identity decision can be
-- re-argued years later on the evidence rather than on a score. NOTE (ADR 0042): if any of this
-- is ever hashed into the custody ledger, IEEE-754 floats are banned from the canonical payload
-- profile — serialise them as decimal strings. `match_score FLOAT8` is fine as a column; it must
-- not travel into `canon_bytes`.
--
-- `match_score_bounded` REFUSES A SCORE OUTSIDE [0, 1] and tolerates NULL, because 'unmatched'
-- and 'opaque_control' have no score to report and a sentinel like -1 is a number that later gets
-- averaged.
--
-- UNVERIFIED ON THIS MACHINE: no CockroachDB v26.2 was reachable when this band was authored, so
-- this statement has not been executed. See tests/integration/schema/test_mi_spine.py.

CREATE TABLE mainline.identity_residue (
  residue_id             UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_id                UUID        NOT NULL,
  commit_id              BYTES       NOT NULL,
  ancestor_clause_uuid   UUID        NOT NULL,
  reason                 STRING      NOT NULL,
  max_ancestral_severity INT2        NOT NULL,   -- PROJECTED via mainline.clause_blame_current (P2)
  match_score            FLOAT8      NULL,
  features               JSONB       NOT NULL,   -- the arithmetic, kept
  disposition_id         UUID        NULL,       -- NULL ⇒ blocking. FK deferred to band 0200-0279.
  first_seen             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_residue_pk PRIMARY KEY (residue_id),
  CONSTRAINT residue_unique UNIQUE (commit_id, ancestor_clause_uuid, reason),
  CONSTRAINT fk_commit FOREIGN KEY (commit_id) REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT fk_ancestor_clause FOREIGN KEY (ancestor_clause_uuid)
    REFERENCES mainline.clause (clause_uuid),
  CONSTRAINT reason_closed CHECK (reason IN
    ('unmatched', 'ambiguous', 'anchor_drop', 'opaque_control', 'citation_unresolved')),
  CONSTRAINT severity_range CHECK (max_ancestral_severity BETWEEN 0 AND 5),
  CONSTRAINT match_score_bounded
    CHECK (match_score IS NULL OR (match_score >= 0.0 AND match_score <= 1.0)),
  INDEX ir_open (site_id, commit_id) WHERE disposition_id IS NULL
);
