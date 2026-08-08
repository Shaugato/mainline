-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI22
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: DIRECTRIX — the two columns that decide which way a setpoint move is dangerous are the highest-leverage state in the product, so they are not a table anybody can UPDATE; they are clauses in the gated commit DAG, and this view is the read surface over them. I06 applied to a lookup: nothing is stored twice, so there is no second copy that can disagree with the clause the gate read.
--
-- migration:  0150_v_safe_direction_current
-- domain:     algorithms
-- band:       0150-0154 · algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), which grants
--             0150-0154 to the algorithms domain for `mainline.*` business views and names
--             `v_safe_direction_current = 0150` as the head of the band.
-- statements: 1
-- invariants: MI22 — the gate fails closed on a stale or absent projection.
--             I06  — a dependency a gate consumes is COMPUTED, never declared.
-- source:     ARCHITECTURE.md §5.2 (commit_obj, doc) · §5.3 (clause, clause_version)
--             docs/leads/algorithms.md §2 DIRECTRIX, §9 (written as 0207; RELOCATED to 0150 by
--             docs/leads/migration-reconciliation.md §5.4 and MR-7)
--             research/05-architecture/clause-identity.md §6.2
-- requires:   0024 mainline.commit_obj · 0027 mainline.doc · 0028 mainline.clause ·
--             0029 mainline.clause_version
-- sqlstate:   none — this object refuses nothing. See "WHAT THIS IS NOT", below.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THIS FILE IS 0150 AND NOT 0207
-- ─────────────────────────────────────────────────────────────────────────────
-- The algorithms lead allocated itself the band 0200-0219. ARCHITECTURE.md §18
-- ends at 0171 and defines nothing at 0200; datamodel.md separately claimed
-- 0200-0279 for views and RLS. Both claims are revoked (MR-7), 0200+ is
-- UNALLOCATED, and `trappoint migrate lint` rule B refuses a file that claims a
-- number no band grants.
--
-- 0150 is not just the nearest legal address, it is the right stratum. A view is
-- a stored query, and a stored query must be created AFTER every trigger that
-- can change what it reads — otherwise the view exists during a window in which
-- the rows behind it are not yet being maintained, and a reader that runs in
-- that window gets an answer the schema does not yet stand behind. 0150 follows
-- the whole function band (0100-0144) and the whole trigger band (0115-0149),
-- which is what "business view" means positionally. This view is a business
-- view and not an audit view: it lives in schema `mainline`, not
-- `mainline_audit`, so it takes the head of the 0150-0154 business-view band
-- rather than a number in 0155-0169.
--
-- Nothing below this line changed in the relocation. The SQL body is
-- byte-for-byte what was verified at 0207.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- THE POINT: THERE IS NO safe_direction TABLE, AND THAT IS THE MECHANISM
-- ─────────────────────────────────────────────────────────────────────────────
-- safe_direction(parameter) decides which way a setpoint move is dangerous. It
-- is the input to lattice rule R2, and R2 decides whether an edit is a
-- weakening, and a weakening over blood-written ancestry is what the merge gate
-- refuses on. So the direction table is the highest-leverage two columns in the
-- product.
--
-- Held as an ordinary table, the cheapest possible attack on MAINLINE would be:
--
--     UPDATE mainline.safe_direction
--        SET direction = 'higher_is_safer'
--      WHERE parameter = 'max_operating_pressure';
--
-- After which every pressure increase classifies as `strengthen`, nothing
-- raises, no residue appears, no check opens, and the gate keeps working
-- perfectly while giving the opposite answer. Grants and audit logs do not fix
-- that: they make the edit attributable afterwards, and this product's claim is
-- that the database REFUSES, not that somebody can reconstruct who broke it.
--
-- So there is no table. Each parameter is a CLAUSE in a document
-- (doc_code = 'REG-SAFE-DIRECTION') inside the same gated commit DAG the
-- procedures live in. Editing a direction is therefore a change_request against
-- a protected branch; the entry carries blame edges like any other clause, so a
-- direction written after a fatality is answerable to that fatality; and the
-- ratifying act is a signed commit rather than an UPDATE. The gate's own
-- parameters are gated by the gate. That recursion is DIRECTRIX.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS
-- ─────────────────────────────────────────────────────────────────────────────
-- A readable projection of the registry AS IT STANDS NOW, for the console, the
-- Managed-MCP read surface and the operator answering "what does this site say
-- about max_operating_pressure today". Current means `clause.head_commit`.
--
-- Every column except the identifiers is DERIVED FROM THE CLAUSE TEXT by string
-- extraction. Nothing is stored twice. That is I06 applied to a lookup rather
-- than to a dependency edge: a `direction` column maintained alongside the
-- clause could disagree with the clause, and the moment those two can disagree
-- the interesting question becomes which one the gate read.
--
-- `split_part` and not a regex: CockroachDB's `substring(… FROM pattern)`
-- capture-group semantics are not something this migration wants to depend on,
-- and the grammar is fixed and delimiter-safe by construction — parameter keys
-- are `[a-z][a-z0-9_]*` and dimension labels and directions are closed
-- vocabularies, so none of them can contain the '.' that terminates its field.
-- The rationale is last and runs to the end of the clause, so it takes
-- everything after its label and needs no terminator.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS IS NOT — read this before citing the view anywhere
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. IT IS NOT WHAT THE GATE READS.
--    The gate resolves a direction AS OF THE COMMIT UNDER TEST, via
--    `mainline_domain.registry.loader.load_registry`, which walks
--    `commit_edge` from that commit. A verdict issued last March must be
--    re-derivable under the registry that existed last March, and a view over
--    `head_commit` answers only about today. Wiring R2 to this view would make
--    every historical verdict silently re-computable under a registry that has
--    moved since — which is the retro-tuning attack M3 exists to prevent,
--    rebuilt by accident in a different column.
--
-- 2. IT REFUSES NOTHING. It is a view; it has no CHECK, no trigger and no
--    SQLSTATE. The refusals DIRECTRIX participates in are the delta lattice's
--    (W4 — migrations 0049a, 0140, 0145) and the merge gate's (kernel lead).
--    Claiming a refusal here would be claiming a mechanism this file does not
--    contain.
--
-- 3. `answers` IS A CONVENIENCE, NOT AN AUTHORITY. It reproduces, in SQL, the
--    conditions the Python loader requires before an entry answers: the clause
--    parses as a registry entry, its status is RATIFIED, the commit carrying it
--    is signed, and the clause is not retired. It is here so that an operator
--    reading the view sees the same set of live parameters the algorithm does,
--    and it is fail-closed in the same direction — anything unparseable,
--    unratified, unsigned or retired reports false. If the two ever disagree,
--    the Python loader is right and this column is a bug, because the loader is
--    the one whose answer reaches a state transition.
--
-- 4. IT IS NOT A SUBSTITUTE FOR RATIFICATION COVERAGE. A parameter absent from
--    this view is not neutral; decision D6 makes it abstain, and an abstention
--    resolves to `weaken`. An empty view therefore blocks everything, which is
--    the correct direction of failure and a very loud one.

CREATE VIEW mainline.v_safe_direction_current AS
  SELECT cv.site_id                                                          AS site_id,
         d.doc_id                                                            AS doc_id,
         d.doc_code                                                          AS doc_code,
         c.clause_uuid                                                       AS clause_uuid,
         cv.commit_id                                                        AS ratification_commit,
         co.author_sub                                                       AS ratified_by_sub,
         co.committed_at                                                     AS ratified_at,
         (co.sig IS NOT NULL)                                                AS ratification_signed,
         cv.gen                                                              AS gen,
         cv.canon_version                                                    AS canon_version,
         cv.canon_sha256                                                     AS canon_sha256,
         split_part(split_part(cv.canon_text, 'Parameter: ', 2), '.', 1)     AS parameter_key,
         split_part(split_part(cv.canon_text, 'Dimension: ', 2), '.', 1)     AS dimension_label,
         split_part(split_part(cv.canon_text, 'Direction: ', 2), '.', 1)     AS direction,
         split_part(split_part(cv.canon_text, 'Status: ', 2), '.', 1)        AS entry_status,
         split_part(cv.canon_text, 'Rationale: ', 2)                         AS rationale,
         (    cv.canon_text LIKE 'SAFE-DIRECTION REGISTRY ENTRY. Parameter: %'
          AND split_part(split_part(cv.canon_text, 'Direction: ', 2), '.', 1) IN
                ('LOWER_IS_SAFER', 'HIGHER_IS_SAFER', 'TIGHTER_TOLERANCE_IS_SAFER')
          AND split_part(split_part(cv.canon_text, 'Status: ', 2), '.', 1) = 'RATIFIED'
          AND co.sig IS NOT NULL
          AND c.retired_commit IS NULL)                                      AS answers,
         cv.canon_text                                                       AS canon_text
    FROM mainline.clause c
    JOIN mainline.clause_version cv
      ON cv.clause_uuid = c.clause_uuid
     AND cv.commit_id   = c.head_commit
    JOIN mainline.doc d
      ON d.doc_id = cv.doc_id
    JOIN mainline.commit_obj co
      ON co.commit_id = cv.commit_id
   WHERE d.doc_code = 'REG-SAFE-DIRECTION';
