-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI13, MI15
-- I: I11, I05
-- COUNSEL-GATED: no
-- RATIONALE: An inferred link is a claim about the past, and a claim about the past that BLOCKS converts every model error directly into a rubber stamp — the single most discoverable exhibit a plaintiff can be handed — so `inference_never_blocks` is a plain-column CHECK rather than a service rule, because the writer it constrains is our own agent fleet and enforcement the constrained party can decline to call is not enforcement.
--
-- migration:  0037_blame_edge
-- band:       0032-0039 · dm-blame · AUTHORED (activity taxonomy, events, the blame DAG and its
--             closure), allocated by verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.4 (verbatim shape; constraints named per DM-10, indexes inline
--             per DM-6) · §4 the BLAME DAG diagram · §16 MI13 · §6.4 channel A
-- requires:   0014 mainline.blame_basis · 0015 mainline.blame_state · 0024 mainline.commit_obj ·
--             0027 mainline.doc · 0028 mainline.clause · 0033 mainline.event
-- consumed:   0038 clause_blame_closure (the recursive walk's BASE CASE reads this table) ·
--             queries/closure_write.sql · §6.4 channel A · mainline.identity_residue (0049)
-- sqlstate:   23514 on inference_never_blocks / asserted_needs_quote / human_needs_signature /
--             scored_needs_features and the shape CHECKs; 23503 on fk_event / fk_clause /
--             fk_commit / fk_evidence_doc; 23505 on blame_edge_pk
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- BASIS-GRADED FORCE. THE SINGLE MOST IMPORTANT LINE IN §5.4.
--     CONSTRAINT inference_never_blocks
--       CHECK (basis <> 'inferred_semantic' OR state <> 'active')
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHAT THIS TABLE IS. One row says: *this event wrote this clause*. It is the blame pointer the
-- whole product is named for — every clause of a procedure, setpoint or critical control carries
-- a pointer back to the incident that wrote it — and `mainline.clause_blame_closure` (0038) is
-- nothing but the transitive closure of this table over `mainline.event_edge` (0034).
--
-- FOUR BASES, AND THEY ARE NOT FOUR CONFIDENCES OF THE SAME CLAIM. They are four DIFFERENT
-- CLAIMS, distinguished by who can be cross-examined about them:
--
--   asserted_document    the source document says so, in words, at a byte range we can quote.
--                        `asserted_needs_quote` refuses one without the digest of those bytes:
--                        an assertion whose quote cannot be produced is hearsay with a schema.
--   asserted_human       a named person signed for the link. `human_needs_signature` refuses one
--                        without `review_sig`, because "a human reviewed it" with no signature is
--                        a claim about a person made by whoever wrote the row.
--   derived_documentary  re-derivable: the intersection of this event's `control_failure`
--                        classes with the clause's Control Assertion Tuple is non-empty. A
--                        machine computed it and a machine can recompute it, which is why it is
--                        allowed to block — it is checkable, not believable.
--   inferred_semantic    a model thought these were about the same thing. NEVER `active`.
--
-- WHY `inferred_semantic` IS PERMITTED TO EXIST AT ALL. Deleting it would be the easy answer and
-- the wrong one: the inference is often RIGHT, and it is the cheapest way to find the 2004
-- fatality nobody remembered. So it is recorded, shown, argued with, and promoted by a person who
-- signs for it — at which point it is a DIFFERENT ROW with `basis = 'asserted_human'`, because
-- `basis` is in the PRIMARY KEY. Promotion is an insert with a signature, never an UPDATE, and
-- the machine's original guess stays visible beside the human's endorsement of it. What an
-- `inferred_semantic` edge may never do is reach `active`, and therefore it may never enter the
-- closure's recursive walk (`queries/closure_write.sql` filters `state = 'active'` in its base
-- case), and therefore it may never raise `clause_blame_closure.max_severity`. That chain —
-- CHECK, then filter, then scalar — is what makes "a model error cannot arm a gate" a property of
-- the cluster rather than a paragraph in a design document.
--
-- The one thing an inferred edge DOES block is stated in §5.4 and is not enforced here: a commit
-- whose `control_delta = 'weaken'` landing on the clause it points at. That is the merge gate's
-- job (band 0100-0135), it reads this table by `clause_uuid`, and it is named here so the
-- absence of enforcement in this file is a recorded fact rather than an oversight.
--
-- `basis` IS IN THE PRIMARY KEY, AND THAT IS LOAD-BEARING. `PRIMARY KEY (clause_uuid, event_id,
-- basis)` means one (event, clause) pair may carry up to four rows, one per basis, and they
-- coexist. A document asserted the link, a model inferred it, and a person signed for it: three
-- independent claims about the same past, each with its own state, its own evidence and its own
-- author. Collapsing them onto one row would force a *choice* of basis at write time and would
-- destroy the only record that answers "did a human agree with the machine, or was the machine
-- alone?" — which is the first question in cross-examination.
--
-- `scored_needs_features` IS THE ANTI-BARE-NUMBER RULE. A `derived_documentary` or
-- `inferred_semantic` edge must carry `p_link`, and `features` is NOT NULL for every row, so a
-- score always arrives with the evidence that produced it. `attribution` is the prose a human is
-- shown — §5.4's words — and `attribution_is_prose` is crude on purpose, in the same spirit as
-- 0036's `substantive`: twelve characters is longer than "0.83" and longer than "match", and a
-- length CHECK is row-local, immutable, needs no service, and cannot be talked out of at 3 a.m.
-- It does not make the attribution good. It makes a bare number a refusal instead of a caption.
--
-- `inferred_names_its_model` IS THE SAME PRINCIPLE AS 0029's `model_named_when_model_used`, and
-- it is repeated here rather than assumed: a row that claims a model produced it without naming
-- the model cannot be re-run, cannot be attributed to a prompt version, and cannot be withdrawn
-- when that model is found to be wrong about a class of incidents. The recall of a bad model's
-- output is a fleet-wide operation keyed on exactly this column.
--
-- ── STRICTLY STRONGER THAN §5.4, AND WHY EACH ADDITION IS CHEAP ───────────────────────────────
--
--   fk_evidence_doc            §5.4 leaves `evidence_doc_id` a bare UUID. A dangling one means
--                              the quote that justifies a blame edge cannot be located, which is
--                              indistinguishable from there never having been one. MATCH SIMPLE
--                              accepts NULL, so an edge with no document evidence is unaffected.
--   evidence_span_is_a_pair    `INT8[2]` is documentation that looks like a constraint — neither
--                              PostgreSQL nor CockroachDB enforces an array dimension. Same
--                              correction, same spelling, as 0035.
--   evidence_span_needs_a_digest
--                              a span with no digest is a pointer nobody can verify — the bytes
--                              at those offsets may have been re-extracted since. The converse is
--                              DELIBERATELY NOT refused: a digest with no span is still a
--                              verifiable commitment to the quoted bytes, and `derived_documentary`
--                              edges routinely carry one without an offset because the quote came
--                              from a `control_failure` row that holds the span itself. A
--                              biconditional here would refuse a legal row for symmetry's sake.
--   review_is_attributed       a signature with nobody's name on it is not a signature.
--   p_link_is_a_probability    a score outside [0,1] is a score that was never calibrated, and
--                              §6.4's admission thresholds (τ(5)=0.35 … τ(1)=0.85) are compared
--                              against it directly.
--   commit_id_is_sha256        the spine's spelling (0024, 0029, 0036), followed rather than
--                              re-invented.
--
-- ── A RECORDED ABSENCE: `provisional_until` CARRIES NO CHECK ──────────────────────────────────
--
-- The obvious constraint — `state <> 'provisional' OR provisional_until IS NOT NULL` — is NOT
-- here, and the absence is a decision. `state` DEFAULTs to `provisional`, so that CHECK would
-- make the default value unwritable and every ingest would have to invent a review deadline for
-- an edge nobody has looked at yet. Worse, an inferred edge is provisional *permanently* by
-- construction (MI13 forbids it ever going active), so a mandatory deadline on it would be a
-- deadline that means nothing and is renewed forever. The review SLA is the steward agent's, it
-- is measured against `provisional_until` where one is set, and it is not a property of the row.
--
-- ── PLATFORM CORRECTION TO THE INDEX AS PRINTED IN §5.4 ──────────────────────────────────────
--
-- §5.4 prints `INDEX by_event (site_id, event_id) STORING (basis, state, p_link)`. `basis` is a
-- PRIMARY KEY column, and CockroachDB refuses a primary-key column in a `STORING` clause;
-- secondary indexes carry the primary key implicitly, so the column is present regardless and
-- nothing is lost by dropping it from the list. This is the same correction 0024's
-- `by_branch_gen` and 0029's `by_commit` already record, followed here rather than rediscovered.
--
-- `by_clause_commit` IS ADDED AND IT IS THE CLOSURE WRITER'S ACCESS PATH. The recursive CTE in
-- `verticals/mainline/db/queries/closure_write.sql` opens with
--
--     WHERE b.clause_uuid = $1 AND b.commit_id = $2 AND b.state = 'active'
--
-- and every one of those three columns is equality-constrained, so the index makes the base case
-- a single constrained scan instead of a range scan over every edge of the clause followed by a
-- filter. `queries/EXPLAIN-ASSERTIONS.md` records the expected plan fragment and the test suite
-- asserts it, because a projection whose cost is unbounded is a projection that stops running.
--
-- ── VERIFIED, AND AGAINST WHAT ────────────────────────────────────────────────────────────────
--
-- This statement was APPLIED to a live CockroachDB CCL **v26.2.5** (`cockroachdb/cockroach:
-- latest-v26.2`, build tag v26.2.5, 2026-07-28) on 2026-08-10, after the 62 migrations numbered
-- at or below 0036, all of which also applied cleanly. Two constructs were more than routine and
-- both were measured rather than assumed:
--
--   (i)  ENUM columns compared against string literals inside a CHECK
--        (`basis <> 'asserted_document'`, `basis IN ('asserted_document','asserted_human')`).
--        ACCEPTED. This is ARCHITECTURE's own spelling in §5.4 and in §5.5's `waiver_authority`;
--        CockroachDB coerces a string literal to a user-defined ENUM in a comparison. Should a
--        later version refuse it, the one-line remediation is `basis::STRING <> 'asserted_document'`
--        — the enum-to-string cast is immutable — and the constraint NAMES do not move, which is
--        what the conformance corpus asserts.
--   (ii) `INDEX … STORING (state, p_link)` where `state` is an ENUM. ACCEPTED.
--
-- What was NOT dropped from the printed §5.4 form and had to be: `STORING (basis, …)`. See the
-- platform correction above. The DM-10 constraint names and every refusal in this file are
-- executed by tests/integration/schema/test_mi_blame.py, which reports a SKIP with a reason
-- rather than a pass when no cluster is reachable.

CREATE TABLE mainline.blame_edge (
  event_id              UUID        NOT NULL,
  clause_uuid           UUID        NOT NULL,
  basis                 mainline.blame_basis NOT NULL,   -- four claims, not four confidences
  state                 mainline.blame_state NOT NULL DEFAULT 'provisional',
  site_id               UUID        NOT NULL,   -- authoritative source: mainline.site (DM-3)
  commit_id             BYTES       NOT NULL,   -- the commit in which this link was recorded
  p_link                FLOAT8      NULL,       -- calibrated; §6.4 compares τ against it directly
  features              JSONB       NOT NULL,   -- the evidence the score was computed from
  attribution           STRING      NULL,       -- prose a human is shown; never a bare number
  evidence_doc_id       UUID        NULL,
  evidence_span         INT8[2]     NULL,       -- dimension is decoration; the CHECK enforces
  evidence_quote_sha256 BYTES       NULL,
  provisional_until     TIMESTAMPTZ NULL,       -- see the recorded absence above
  reviewed_by           STRING      NULL,
  review_sig            BYTES       NULL,
  reviewed_at           TIMESTAMPTZ NULL,
  model_id              STRING      NULL,
  prompt_version        STRING      NULL,
  CONSTRAINT blame_edge_pk PRIMARY KEY (clause_uuid, event_id, basis),
  CONSTRAINT fk_event FOREIGN KEY (event_id) REFERENCES mainline.event (event_id),
  CONSTRAINT fk_clause FOREIGN KEY (clause_uuid) REFERENCES mainline.clause (clause_uuid),
  CONSTRAINT fk_commit FOREIGN KEY (commit_id) REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT fk_evidence_doc FOREIGN KEY (evidence_doc_id) REFERENCES mainline.doc (doc_id),
  -- MI13. BASIS-GRADED FORCE. An inferred link is a claim about the past; making it block
  -- converts every model error into a rubber stamp.
  CONSTRAINT inference_never_blocks
    CHECK (basis <> 'inferred_semantic' OR state <> 'active'),
  CONSTRAINT asserted_needs_quote
    CHECK (basis <> 'asserted_document' OR evidence_quote_sha256 IS NOT NULL),
  CONSTRAINT human_needs_signature
    CHECK (basis <> 'asserted_human' OR review_sig IS NOT NULL),
  CONSTRAINT scored_needs_features
    CHECK (basis IN ('asserted_document', 'asserted_human') OR p_link IS NOT NULL),
  CONSTRAINT inferred_names_its_model
    CHECK (basis <> 'inferred_semantic' OR model_id IS NOT NULL),
  CONSTRAINT p_link_is_a_probability
    CHECK (p_link IS NULL OR (p_link >= 0.0 AND p_link <= 1.0)),
  CONSTRAINT evidence_span_is_a_pair
    CHECK (evidence_span IS NULL OR array_length(evidence_span, 1) = 2),
  CONSTRAINT evidence_quote_is_a_digest
    CHECK (evidence_quote_sha256 IS NULL OR length(evidence_quote_sha256) = 32),
  CONSTRAINT evidence_span_needs_a_digest
    CHECK (evidence_span IS NULL OR evidence_quote_sha256 IS NOT NULL),
  CONSTRAINT review_is_attributed
    CHECK (review_sig IS NULL OR reviewed_by IS NOT NULL),
  CONSTRAINT review_sig_present
    CHECK (review_sig IS NULL OR length(review_sig) > 0),
  CONSTRAINT attribution_is_prose
    CHECK (attribution IS NULL OR length(attribution) >= 12),
  CONSTRAINT commit_id_is_sha256 CHECK (length(commit_id) = 32),
  INDEX by_event (site_id, event_id) STORING (state, p_link),
  INDEX by_clause_commit (clause_uuid, commit_id, state),
  INDEX by_state (site_id, state, provisional_until)
);
