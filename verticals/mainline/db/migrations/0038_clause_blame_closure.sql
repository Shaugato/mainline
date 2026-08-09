-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI26, MI22, MI25
-- I: I05, I02
-- COUNSEL-GATED: no
-- RATIONALE: Adversarial finding S2: every ancestry-conditioned gate in MAINLINE reads one scalar off this table, and the table as originally specified was mutable, so a single UPDATE was a shorter path to a laundered permit than any attack the rest of the design was defending against — the fix is structural rather than procedural, and it is this file: the primary key carries the generation, so a recomputation is a NEW ROW and the closure that armed a check last year is still readable this year.
--
-- migration:  0038_clause_blame_closure
-- band:       0032-0039 · dm-blame · AUTHORED (activity taxonomy, events, the blame DAG and its
--             closure), allocated by verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.4 (verbatim shape; constraints named per DM-10, indexes inline
--             per DM-6) · §2.2 finding S2 · §16 MI26 · §8 the `closure-projector` agent
-- requires:   0013 mainline.virulence_class · 0029 mainline.clause_version
--             (specifically its `cv_clause_commit_unique UNIQUE (clause_uuid, commit_id)`)
-- consumed:   0039 mainline.clause_blame_current — THE ONLY READ PATH (DM-9) ·
--             0108 fn_closure_guard (dense + monotone + ledgered) welded by 0127 ·
--             0128j the append-only weld · queries/closure_write.sql (the writer) ·
--             fn_check_project (MI25) and the merge gate (MI22), which read the VIEW
-- sqlstate:   23514 on sev_range / gen_positive / truncation_is_declared /
--             count_matches_the_array / virulence_is_banded_from_severity and the shape CHECKs;
--             23503 on fk_version; 23505 on clause_blame_closure_pk;
--             P0001 from fn_closure_guard (0108) and fn_refuse_mutation (0107) once welded
-- grants:     agent_projector holds INSERT on this table AND NOTHING ELSE (S2). There is NO
--             UPDATE and NO DELETE grant on this table for any role, anywhere, ever — grants are
--             cluster state applied by verticals/mainline/db/GRANTS.yaml, never by a migration,
--             and this line is the statement of what that matrix must say.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE TABLE UNDER EVERY ANCESTRY GATE. APPEND-ONLY, GENERATION-VERSIONED, MONOTONE.
--     PRIMARY KEY (clause_uuid, as_of_commit, closure_gen)
-- A recomputation is a NEW GENERATION, never an overwrite.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHY THE CLOSURE IS MATERIALISED AT ALL, STATED CORRECTLY. Not because CTEs are illegal inside
-- routines — they have been legal since v25.1 and the platform ground truth (F3) measures them
-- passing. Three reasons, in order of force:
--
--   1. A `CHECK` can consume a PROJECTED SCALAR and nothing else. §4.1 law 1: a CHECK sees only
--      the row being written. `max_severity` is that scalar, and `virulence` is its band.
--   2. The gate transaction's p99 is a product requirement. An unbounded recursive walk inside a
--      hot trigger is not `EXPLAIN`-assertable and its cost is a function of a customer's data.
--   3. A materialised generation is EVIDENCE. "What did this system believe about this clause's
--      ancestry on the day it refused that permit" is answerable by primary-key lookup, months
--      later, on a cluster whose `AS OF SYSTEM TIME` window is seventy-five minutes (F2).
--
-- THE WRITER IS A TOP-LEVEL APPLICATION STATEMENT, NOT A TRIGGER, AND THIS IS A TRAP TO AVOID.
-- `verticals/mainline/db/queries/closure_write.sql` is the committed statement; it is driven by
-- the outbox changefeed and executed by the `closure-projector` Lambda as `agent_projector`.
-- DO NOT ADD A TRIGGER THAT WRITES THIS TABLE. The projection is deliberately ASYNCHRONOUS, and
-- the consequence is deliberately harsh: the gate FAILS CLOSED on a missing or stale closure
-- (MI22), because a permit that merges while the projector is behind is a permit that merged
-- without its ancestry. The two triggers that DO exist on this table (0127 `closure_guard`,
-- 0128j `append_only`) constrain the writer; they do not perform the write.
--
-- ── `truncated`, AND WHY IT IS THE MOST IMPORTANT BOOLEAN IN THE SCHEMA ───────────────────────
--
-- A truncated closure MUST NEVER BE INDISTINGUISHABLE FROM A COMPLETE ONE. A closure that hit
-- either bound has walked LESS ancestry than exists, so its `max_severity` is a LOWER BOUND, and
-- a lower bound presented as a fact understates severity — the one error direction with physical
-- consequences. Two bounds, two causes, one flag:
--
--   depth  ≥ 64   `queries/closure_write.sql` ends its recursion at `depth < 64` because
--                 CockroachDB has no `CYCLE` clause, so the depth cap is the ONLY cycle guard
--                 the walk has. A row at depth 64 exists if and only if the walk stopped at the
--                 bound, which makes `depth_truncation_is_declared` below EXACT.
--   count ≥ 512   above 512 ancestors the array is capped, the overflow spills to a side table
--                 and a silence-ledger row is written.
--
-- `truncation_is_declared` is stated as `truncated OR (ancestor_count < 512 AND depth < 64)`,
-- with a STRICT `<` on the count, and the strictness is deliberate. A complete closure holding
-- exactly 512 ancestors and a truncated one holding its first 512 are THE SAME ROW — no CHECK
-- can separate them — so the writer declares truncation at `>= 512` rather than `> 512`. The
-- cost is over-declaring truncation for a closure that happens to have exactly 512 ancestors;
-- the benefit is that the CHECK is exact in the direction that matters. Over-declaring
-- incompleteness is safe. Under-declaring it is the failure this column exists to prevent.
--
-- ── `virulence` IS BANDED ONCE, HERE, AND THE BANDING IS ENFORCED IN THE ARMING DIRECTION ─────
--
-- Every downstream `virulence` in MAINLINE — `blocking_check.virulence`, the clearance lattice's
-- composite FK, the console's severity ramp — is a PROJECTION of this column (MI25). "Banded
-- once, here" is worth nothing if the writer can choose the band, because the writer is our own
-- agent and P2's whole content is that a gate reads columns whose provenance is enforced. Three
-- one-directional CHECKs pin it:
--
--   fatal_ancestry_is_banded_fatal        max_severity 5 ⇒ virulence = 'blood_fatal'
--   major_ancestry_is_at_least_major      max_severity 4 ⇒ virulence ∈ {blood_major, blood_fatal}
--   blood_needs_severity                  virulence ∈ {blood_major, blood_fatal} ⇒ severity ≥ 4
--
-- They refuse UNDER-banding and permit OVER-banding, on purpose. Banding a severity-4 ancestry
-- as `blood_fatal` raises the bar and costs a signature; banding a severity-5 ancestry as
-- `routine` would make `(blood_fatal, mechanism_absent)`'s deliberate absence from
-- `clearance_legal` bypassable by one integer, which is the entire clearance lattice defeated
-- from the projector. Below severity 4 the band is free — `routine` versus `serious` has no gate
-- consequence anywhere in this system (every ancestry law quantifies over `max_severity >= 4`),
-- and inventing a threshold ARCHITECTURE never states would be a second, softer copy of a
-- number that already exists in exactly one place.
--
-- ── `count_matches_the_array` — THE COUNT MAY NOT DISAGREE WITH THE ARRAY ─────────────────────
--
-- `ancestor_count` exists so that a reader can size an ancestry without deserialising a `UUID[]`,
-- and a denormalised count that may drift from the thing it counts is a lie waiting for a
-- deadline. `array_length` on an empty array returns NULL, not 0 — hence the `coalesce` — and a
-- closure with zero ancestors is entirely legal and meaningful: it is the INERT case, and it is
-- distinguishable from an ABSENT projection, which is precisely what MI22 needs.
--
-- ── THE COMPOSITE FK, AND WHY IT IS `RESTRICT` ON BOTH SIDES ──────────────────────────────────
--
-- `(clause_uuid, as_of_commit) → clause_version (clause_uuid, commit_id)` resolves against
-- 0029's `cv_clause_commit_unique`. A closure is *about a version of a clause*, never about a
-- clause in the abstract, and this FK is what makes that unforgeable: there is no way to record
-- an ancestry for a clause text that was never committed. `ON UPDATE RESTRICT ON DELETE RESTRICT`
-- adds a second, independent refusal beneath 0128i's append-only weld on `clause_version` — the
-- conformance suite's unwelding matrix requires refusal depth ≥ 2 on the gate path, and a
-- clause version deleted out from under the closure that armed a live check is exactly the
-- history that must fail twice.
--
-- ── PLATFORM CORRECTION TO THE INDEXES AS PRINTED IN §5.4 ────────────────────────────────────
--
-- §5.4 prints:
--
--     CREATE INDEX cbc_sev ON mainline.clause_blame_closure (site_id, max_severity)
--       STORING (clause_uuid, virulence, closure_gen);
--
-- `clause_uuid` and `closure_gen` are PRIMARY KEY columns, and CockroachDB refuses a primary-key
-- column inside a `STORING` clause. Secondary indexes carry the primary key implicitly, so both
-- columns are present in the index regardless and the STORING list correctly reduces to
-- `(virulence)`. This is the same correction 0024's `by_branch_gen` and 0029's `by_commit`
-- already record; it is followed here rather than rediscovered at apply time.
--
-- `cbc_anc` is the multi-column inverted index and its shape is not a preference:
-- **the inverted column is LAST and it carries no `STORING` clause** — CockroachDB accepts a
-- multi-column inverted index only in that order and refuses `STORING` on one entirely. It is
-- what makes *"which clauses inherit incident E?"* an index lookup rather than a scan:
--
--     ancestor_events @> ARRAY[$2::UUID]
--
-- `queries/closure_read.sql` is that lookup and `queries/EXPLAIN-ASSERTIONS.md` records both the
-- expected plan fragment AND the one place the claim is weaker than §5.4 states it. Read that
-- file before quoting the sentence "one index lookup" anywhere a regulator can hear it.
--
-- Both indexes are declared INLINE (DM-6), which also means they exist from row zero: an index
-- created after the table is populated is an index whose build can fail on a customer's data.
--
-- ── VERIFIED, AND AGAINST WHAT ────────────────────────────────────────────────────────────────
--
-- This statement was APPLIED to a live CockroachDB CCL **v26.2.5** (`cockroachdb/cockroach:
-- latest-v26.2`, build tag v26.2.5, 2026-07-28) on 2026-08-10, on top of the 62 migrations
-- numbered at or below 0036 plus 0037. Three constructs were more than routine and all three
-- were measured rather than assumed:
--
--   (i)   `INVERTED INDEX cbc_anc (site_id, ancestor_events)` declared INLINE in `CREATE TABLE`,
--         MULTI-COLUMN, inverted column last, no `STORING`. ACCEPTED, and measured to be
--         traversed for `ancestor_events @> ARRAY[$2::UUID]` — `table:
--         clause_blame_closure@cbc_anc · spans: 1 span` — both with the index pinned and, at
--         demo-corpus scale, without. Should a later version refuse the inline multi-column form,
--         the remediation is one new file `0038a_cbc_anc.sql` carrying the standalone
--         `CREATE INVERTED INDEX`; the band owns its own letter space, so no neighbour is
--         disturbed (MR-5 band overflow).
--   (ii)  `coalesce(array_length(ancestor_events, 1), 0)` inside a CHECK. ACCEPTED, and the
--         refusal it produces is a plain `23514` naming `count_matches_the_array`.
--   (iii) ENUM comparison against string literals in a CHECK (`virulence = 'blood_fatal'`,
--         `virulence NOT IN (...)`). ACCEPTED — ARCHITECTURE's own spelling in §5.5's
--         `waiver_authority`. If a later version refuses it, `virulence::STRING = 'blood_fatal'`
--         is the remediation and the constraint NAMES do not move.
--
-- The measured plans for both indexes, and the one place ARCHITECTURE §5.4 overstates what the
-- read path costs, are in `verticals/mainline/db/queries/EXPLAIN-ASSERTIONS.md`.

CREATE TABLE mainline.clause_blame_closure (
  clause_uuid     UUID        NOT NULL,
  as_of_commit    BYTES       NOT NULL,   -- the clause VERSION this ancestry is about
  closure_gen     INT8        NOT NULL,   -- monotone and DENSE per (clause_uuid, as_of_commit)
  site_id         UUID        NOT NULL,   -- authoritative source: mainline.site (DM-3)
  ancestor_events UUID[]      NOT NULL,   -- transitive, deduped, ACTIVE edges only
  ancestor_count  INT4        NOT NULL,   -- may not disagree with the array above
  max_severity    INT2        NOT NULL,   -- THE SCALAR EVERY ANCESTRY GATE READS
  virulence       mainline.virulence_class NOT NULL,   -- banded ONCE, here
  depth           INT4        NOT NULL,   -- 64 ⇔ the walk stopped at its only cycle guard
  truncated       BOOL        NOT NULL DEFAULT false,  -- the most important boolean here
  computed_by     STRING      NOT NULL,   -- agent_identity of the projector
  projector_ver   STRING      NOT NULL,   -- the code version that produced this generation
  computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT clause_blame_closure_pk PRIMARY KEY (clause_uuid, as_of_commit, closure_gen),
  CONSTRAINT fk_version FOREIGN KEY (clause_uuid, as_of_commit)
    REFERENCES mainline.clause_version (clause_uuid, commit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT sev_range CHECK (max_severity BETWEEN 0 AND 5),
  CONSTRAINT gen_positive CHECK (closure_gen >= 0),
  CONSTRAINT depth_nonneg CHECK (depth >= 0),
  CONSTRAINT depth_within_cap CHECK (depth <= 64),
  CONSTRAINT ancestor_count_nonneg CHECK (ancestor_count >= 0),
  CONSTRAINT ancestor_count_within_cap CHECK (ancestor_count <= 512),
  -- A truncated closure must never be indistinguishable from a complete one.
  CONSTRAINT truncation_is_declared
    CHECK (truncated = true OR (ancestor_count < 512 AND depth < 64)),
  CONSTRAINT count_matches_the_array
    CHECK (ancestor_count = coalesce(array_length(ancestor_events, 1), 0)),
  -- The banding is enforced in the arming direction only: under-banding is refused,
  -- over-banding is permitted, because understating severity is the error with consequences.
  CONSTRAINT fatal_ancestry_is_banded_fatal
    CHECK (max_severity < 5 OR virulence = 'blood_fatal'),
  CONSTRAINT major_ancestry_is_at_least_major
    CHECK (max_severity < 4 OR virulence IN ('blood_major', 'blood_fatal')),
  CONSTRAINT blood_needs_severity
    CHECK (virulence NOT IN ('blood_major', 'blood_fatal') OR max_severity >= 4),
  CONSTRAINT as_of_commit_is_sha256 CHECK (length(as_of_commit) = 32),
  CONSTRAINT computed_by_stated CHECK (computed_by <> ''),
  CONSTRAINT projector_ver_stated CHECK (projector_ver <> ''),
  INDEX cbc_sev (site_id, max_severity) STORING (virulence),
  INVERTED INDEX cbc_anc (site_id, ancestor_events)
);
