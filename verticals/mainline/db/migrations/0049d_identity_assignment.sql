-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0049d_identity_assignment.sql
-- CREATE TABLE mainline.identity_assignment — the derived edge the conservation law counts
--
-- MI: MI03, MI25
-- I: I06, I02
-- COUNSEL-GATED: no
-- RATIONALE: `identity_residue` (0049) records the ancestors the matcher COULD NOT place. This
--            table records the ones it COULD, and the two together are what makes CONSERVATION
--            OF BLAME MASS arithmetic rather than narrative: `fn_cbm_account_guard` (0140a)
--            re-derives `carried`, `split_carried` and `merge_carried` by grouping THIS relation
--            by `ancestor_clause_uuid` and asking `bool_or(relation = 'matched' | 'split' |
--            'merge')`, and an ancestor in neither relation falls out of every bucket, makes the
--            sum short, and is refused by `CONSTRAINT cbm_balances` at 23514. Without a producer
--            for this table the identity has no positive term at all: every blood-bearing
--            ancestor would be unaccounted and the gate would be a gate that always refuses,
--            which is broken and not safe. Each row is a DERIVED dependency edge (I06) and
--            carries the inputs, method and version that produced it — `score`, `margin`,
--            `stage`, `computed_by` and the content hash of `identity_policy-v1.toml` — so a
--            third party can recompute it, and so retro-tuning the matcher to make a dropped
--            obligation look reasonable is visible the way retro-tuning τ is visible (D11).
--
-- migration:  0049d_identity_assignment
-- domain:     algorithms
-- band:       0049a-0049z · algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). The algorithms
--             table annexe is granted to this domain explicitly and exclusively (MRR-5).
--             `0049a` is `delta_witness`, `0049b` is `commutation_edge`, `0049c` is
--             `cbm_account`; this object takes the next free letter. Two files that predate it
--             say `0049b` in prose — `0049c_cbm_account.sql`'s band note and
--             `0140a_fn_cbm_account_guard.sql`'s `requires:` line, both written when `0049b`
--             was still unclaimed. Those citations are stale, they belong to files this worker
--             does not own, and they are reported rather than edited. The brief's
--             `0200_identity_assignment.sql` is void with the rest of the `0200-0219` annexe
--             (MR-7): `0200`+ is UNALLOCATED and `trappoint migrate lint` rule B refuses it.
-- statements: 1  (the CREATE TABLE, and nothing else; the append-only weld is 0145f)
-- invariants: MI03 — a merged permit carries zero un-dispositioned identity residue. This
--                    relation supplies the POSITIVE terms of the identity that count stands on:
--                    an obligation is discharged by being matched, split or merged, and the
--                    only other legal outcome is a residue row.
--             MI25 — a gate column is a projection, re-derived from the authority relations and
--                    never an input. This table is one of the three authorities 0140a reads;
--                    nothing here lets a writer supply a COUNT, only the individual edges the
--                    count is taken over.
--             I06  — a dependency edge a gate consumes is computed, never declared, and the
--                    derivation's inputs, method and version travel with the edge.
--             I02  — projected refusal: the refusal is a CHECK on a projected scalar, and this
--                    relation is one of the things projected FROM.
-- source:     docs/leads/workers.json · algorithms/margin-assignment · brief item (6), verbatim:
--             "mainline.identity_assignment (site_id, commit_id, ancestor_clause_uuid,
--             descendant_clause_uuid NULL, relation CHECK IN ('matched','split','merge',
--             'absent'), stage, score, margin, policy_sha256, computed_by, computed_at)
--             append-only, PK over (commit_id, ancestor_clause_uuid, coalesced descendant), one
--             DDL statement, header citing MI03/I06."
--             · docs/leads/algorithms.md §1 D11 (the policy hash) and §2 MARGIN ASSIGNMENT
--             · ARCHITECTURE.md §5.3 (identity_residue, the sibling this file is shaped after)
--             · §16 MI03/MI25 · spec/invariants/I06-derived-dependency.md
--             The consumer is authoritative over all of it: 0140a's `asg` CTE selects
--             `g.ancestor_clause_uuid`, filters `g.commit_id = cid`, groups by ancestor and
--             evaluates `bool_or(g.relation = 'split' | 'merge' | 'matched')`. Every column
--             name and type below is the one that query and
--             tests/integration/algorithms/cbm/_cbm_sql_support.py::insert_assignment already
--             use. Nothing here is invented.
-- requires:   0024 mainline.commit_obj · 0028 mainline.clause
-- consumed by: 0140a mainline.fn_cbm_account_guard (the CTE named `asg`), and through it
--             0145a, `mainline.cbm_account.carried / split_carried / merge_carried`, and
--             `mainline_audit.v_cbm_ledger` (0151). CockroachDB v26.2 resolves a PL/pgSQL
--             body's table references at CREATE FUNCTION time only for the FUNCTION's own
--             creation, and resolves the TRIGGER's attachment strictly: measured on this
--             machine, 0140a applied with this table absent and 0145a refused with 42P01. So
--             this file must sort before 0145a, and 0049d < 0145a does.
-- sqlstate:   23503 on fk_commit / fk_ancestor_clause; 23514 on relation_closed /
--             absent_has_no_descendant / commit_id_is_sha256 / policy_sha256_is_sha256 /
--             score_bounded / margin_bounded / stage_stated / computed_by_stated;
--             23505 on identity_assignment_pk; P0001 on UPDATE and DELETE, from 0145f.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE FOUR RELATIONS ARE A CLOSED SET, AND ONE OF THEM COUNTS AS NOTHING
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--   'matched'   the ancestor was placed on exactly one descendant clause in this commit. The
--               obligation survived the edit intact.
--   'split'     the ancestor was placed on SEVERAL descendants — one requirement became two or
--               three. One row per child, so a split writes several rows for one ancestor.
--   'merge'     several ancestors were placed on one descendant. Several obligations were
--               consolidated into one clause.
--   'absent'    the matcher ASSERTS the obligation is gone.
--
-- 'absent' IS IN THE DOMAIN AND IS NOT A BUCKET, AND THAT ASYMMETRY IS THE WHOLE DESIGN.
-- 0140a's five buckets are residue_open, residue_disposed, split_carried, merge_carried and
-- carried. An 'absent' row is in none of them. So a matcher that declares an obligation gone,
-- and writes nothing else, produces an account whose right-hand side is SHORT BY ONE, and
-- `CONSTRAINT cbm_balances` refuses the write at 23514. Declaring an obligation gone is not the
-- same as RECORDING that it is gone: the conservation law says an absent ancestor must be
-- EXPLICITLY absent with a signed disposition, which means a row in `identity_residue` whose
-- `disposition_id` is not NULL. The value exists in this domain so the matcher can say what it
-- concluded, and it earns nothing, so saying it is not a way through.
-- `tests/integration/algorithms/cbm/_cbm_sql_support.py` exercises exactly that as scene
-- disposition `absent_only`, and `test_balance_refusal.py` asserts the 23514.
--
-- WHY THE VALUE IS NOT SIMPLY BANNED. A matcher that ran, considered an ancestor, and concluded
-- it was gone has produced a FINDING, and a schema that gave it nowhere to put that finding
-- would be a schema that turns a conclusion into silence. Silence is indistinguishable from a
-- crashed job (I13), and the two must not be confused: the account is unbalanced either way,
-- but only one of them leaves a row an auditor can read.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `descendant_key` — WHY A NULLABLE COLUMN IS COALESCED INTO A STORED ONE, AND KEYED ON
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- The natural key is (commit_id, ancestor_clause_uuid, descendant_clause_uuid): one verdict per
-- ancestor/descendant pair per commit. But `descendant_clause_uuid` is NULL for 'absent', and a
-- PRIMARY KEY column cannot be NULL. Two escapes were available and both are worse. A synthetic
-- row id would make the table's identity opaque and let the same verdict be written twice, which
-- turns re-running the matcher into double-counting — and 0140a counts ANCESTORS, not rows,
-- precisely because the row count is not the quantity the law is about. A partial UNIQUE index
-- would leave the PK to be invented anyway.
--
-- So the nil UUID stands for "no descendant". It is a real value, it is not a legal
-- `clause_uuid`, and it makes 'absent' exactly one row per (commit, ancestor) — which is the
-- shape the law wants, because an ancestor can be declared absent once and not twice. STORED
-- rather than VIRTUAL because it is a key column and a key must be materialised to be indexed.
-- RE-RUNNING THE MATCHER IS THEREFORE SAFE: the second run's inserts collide on 23505 instead of
-- doubling the evidence, which is the same property `residue_unique` gives 0049.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THERE IS NO FOREIGN KEY ON `descendant_clause_uuid`, AND IT WAS MEASURED, NOT ASSUMED
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- Symmetry with `fk_ancestor_clause` argues for one. The consumer refuses it. The CBM suite's
-- split fixture — `tests/integration/algorithms/cbm/_cbm_sql_support.py::_apply_disposition`,
-- line 832 — writes a split's SECOND child as `descendant=uuid.uuid4()`, a descendant that is
-- deliberately not a `mainline.clause` row, because what the fixture is exercising is "one
-- ancestor, two rows" and the second child's identity is irrelevant to it. A descendant FK would
-- refuse that INSERT with 23503 and take the whole conservation suite red.
--
-- That is a fixture fact, and a fixture is not an authority — but the RULE it exposes is real
-- and is the reason the FK is wrong on its own terms. A split's descendants are written in the
-- same transaction as, and sometimes before, the clause rows they name; the matcher runs over a
-- proposed commit, and the assignment edges are what the commit's clause set is checked AGAINST.
-- A constraint that ordered the assignment after the clause would force the matcher to
-- materialise its conclusion before it was allowed to record it. NEVER ADD A CONSTRAINT THAT
-- CONTRADICTS A CONSUMER: this is a gap and it is recorded here as one, not smoothed over.
-- `fk_ancestor_clause` has no such problem — an ancestor is by definition a clause that already
-- exists in the first-parent commit — and it stays.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `policy_sha256` — D11, AND WHY IT IS NOT NULLABLE
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `identity_policy-v1.toml` holds every threshold, band and ε the matcher used. Its content hash
-- is written onto EVERY row, so the question "was this assignment produced under the policy that
-- was in force at the time" is answerable from the row itself, years later, without trusting a
-- deployment log. Retro-tuning the matcher until a dropped obligation looks reasonable then
-- shows up as a population of rows whose policy hash nobody can produce a file for — the same
-- shape that makes τ-tuning visible in the recall lane (M3).
--
-- NOT NULL and length 32, because a nullable provenance column is a provenance column that is
-- NULL on exactly the rows somebody wanted to be unattributable. `computed_by` and `stage` are
-- non-empty for the same reason: an empty string is a NULL that got past a NOT NULL.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `score` AND `margin` ARE EVIDENCE, BOUNDED, AND NULLABLE
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `score` is the assignment's cost/similarity and `margin` is the distance to the runner-up —
-- the number that decides whether a decision was clear or a coin toss, and the one D4 turns into
-- `ambiguous` residue when it is too small. Both are bounded to [0, 1] where present and both
-- tolerate NULL, because a 'merge' arm or an 'absent' verdict may have no meaningful runner-up
-- and a sentinel like -1 is a number that later gets averaged. This is `match_score_bounded` on
-- 0049, restated for two columns.
--
-- NOTE (ADR 0042): IEEE-754 floats are banned from the canonical payload profile. `score` and
-- `margin` are fine as columns; they must not travel into `canon_bytes` un-serialised as decimal
-- strings.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `by_site_commit` — THE GUARD'S OWN INDEX
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- 0140a asks this table exactly one question per account write: "every assignment row for commit
-- `cid`, grouped by ancestor". That is a per-commit scan on the latency-critical merge path, and
-- the PRIMARY KEY already leads with `commit_id`, so the seek is available without any index at
-- all. `(site_id, commit_id)` is added because every OTHER reader — the console, disclosure, and
-- the RLS predicates that band 0180-0199 will put on this relation — filters by site first, and
-- a site-leading index is what makes those reads a seek rather than a scan over every tenant's
-- history. It is not the gate's index; the primary key is. It is named for the gate because the
-- gate is the reason the table is hot.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHAT THIS FILE DOES NOT DO
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- It does not make the table append-only. `mainline.fn_refuse_mutation` is created at 0107 and
-- welded to this relation at 0145f, one statement per file (MR-5), because CockroachDB DDL is
-- not transactional across statements and one file carrying both would leave an operator unable
-- to tell which half applied. Until 0145f applies, an UPDATE on this table succeeds — and MI03's
-- count would then be editable in place, which is the reason 0145f is not optional.
--
-- It does not enable RLS. That is band 0180-0199's, and `site_id` is here as the scope token
-- those policies will compare against.
--
-- It adds no FK on `site_id`. `identity_residue` (0049) and `cbm_account` (0049c) have none
-- either: `site_id` on all three is the site of the commit, `mainline.commit_obj` already
-- carries the authoritative one, and 0140a PROJECTS the account's `site_id` from that commit
-- rather than trusting the column. A second FK here would assert an authority this column does
-- not have.

CREATE TABLE mainline.identity_assignment (
  site_id                UUID        NOT NULL,   -- scope token; the authority is commit_obj (P2)
  commit_id              BYTES       NOT NULL,   -- the commit whose accounting counts this edge
  ancestor_clause_uuid   UUID        NOT NULL,   -- the obligation being discharged
  descendant_clause_uuid UUID        NULL,       -- NULL ⇔ 'absent'. No FK — see the header.
  relation               STRING      NOT NULL,   -- matched | split | merge | absent
  stage                  STRING      NOT NULL,   -- which cascade stage produced this edge
  score                  FLOAT8      NULL,       -- the arithmetic, kept
  margin                 FLOAT8      NULL,       -- distance to the runner-up; D4's input
  policy_sha256          BYTES       NOT NULL,   -- content hash of identity_policy-v1.toml (D11)
  computed_by            STRING      NOT NULL,   -- the matcher's CLAIM about its own identity
  computed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  descendant_key         UUID        NOT NULL AS (
                           coalesce(descendant_clause_uuid,
                                    '00000000-0000-0000-0000-000000000000'::UUID)
                         ) STORED,
  CONSTRAINT identity_assignment_pk
    PRIMARY KEY (commit_id, ancestor_clause_uuid, descendant_key),
  CONSTRAINT fk_commit FOREIGN KEY (commit_id) REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT fk_ancestor_clause FOREIGN KEY (ancestor_clause_uuid)
    REFERENCES mainline.clause (clause_uuid),
  CONSTRAINT relation_closed CHECK (relation IN ('matched', 'split', 'merge', 'absent')),
  CONSTRAINT absent_has_no_descendant
    CHECK (relation <> 'absent' OR descendant_clause_uuid IS NULL),
  CONSTRAINT commit_id_is_sha256      CHECK (length(commit_id) = 32),
  CONSTRAINT policy_sha256_is_sha256  CHECK (length(policy_sha256) = 32),
  CONSTRAINT computed_by_stated       CHECK (computed_by <> ''),
  CONSTRAINT stage_stated             CHECK (stage <> ''),
  CONSTRAINT score_bounded  CHECK (score  IS NULL OR (score  >= 0.0 AND score  <= 1.0)),
  CONSTRAINT margin_bounded CHECK (margin IS NULL OR (margin >= 0.0 AND margin <= 1.0)),
  INDEX by_site_commit (site_id, commit_id)
);
