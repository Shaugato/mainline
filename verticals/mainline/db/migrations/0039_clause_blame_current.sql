-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI26, MI22, MI25
-- I: I05, I02
-- COUNSEL-GATED: no
-- RATIONALE: DM-9 — this view is the ONLY read path to the blame closure, because `max(closure_gen)` is a discipline every caller owes and an older generation is the generation computed with LESS ancestry, so a single forgotten call site does not error, does not warn, and does not read wrong: it reads a SUPERSEDED severity onto a live blocking check, understating ancestral severity, which is the one error direction with physical consequences.
--
-- migration:  0039_clause_blame_current
-- band:       0032-0039 · dm-blame · AUTHORED (activity taxonomy, events, the blame DAG and its
--             closure), allocated by verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.4 (the view, verbatim in behaviour; the column list is explicit
--             — see below) · docs/leads/datamodel.md DM-9
-- requires:   0038 mainline.clause_blame_closure
-- consumed:   EVERYTHING that reads ancestry. fn_check_project (MI25) · the merge gate (MI22) ·
--             0140b fn_residue_project · 0152 v_blame_origin · the console's ancestry contract ·
--             mainline-cartographer's resolver · queries/closure_read.sql
-- sqlstate:   none — a view refuses nothing. Its job is to make a whole class of reader error
--             unrepresentable by removing the wrong query from the vocabulary.
-- enforcement: scripts/grep_closure_readpath.py. DM-9 is a rule about a name, so its enforcement
--             is a scan over the tree rather than a constraint in the cluster, and it runs in CI.
-- forward-only; a view above the protected floor may carry a .down.sql (DM-14); this one does
-- not, because dropping it would make every reader below it invent its own `max(closure_gen)`.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE ONLY READ PATH TO THE CLOSURE (DM-9).
--     SELECT DISTINCT ON (clause_uuid, as_of_commit) … ORDER BY …, closure_gen DESC
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHY A VIEW RATHER THAN A CONVENTION. `mainline.clause_blame_closure` is append-only and
-- generation-versioned (0038, finding S2): recomputing a closure writes a NEW
-- `(clause_uuid, as_of_commit, closure_gen)` row and overwrites nothing, which is what keeps last
-- year's closure — the one that armed last year's refusal — readable this year. The price of
-- that property is that every reader now owes the discipline `max(closure_gen)`.
--
-- A discipline owed by every call site is a discipline that will be forgotten by one of them, and
-- the forgetting is SILENT. There is no error, no warning, and no wrong-looking result: the query
-- returns a real row from a real generation, just not the current one. An older generation is by
-- construction the generation computed with LESS ancestry — fewer active blame edges had landed,
-- or the event DAG had fewer edges — so its `max_severity` is lower or equal. The failure mode is
-- therefore *always* in the direction of understating ancestral severity, and understating
-- severity is the one error direction in this product with physical consequences.
--
-- So the discipline stops being per-call-site. One relation carries it; the grep in
-- `scripts/grep_closure_readpath.py` fails CI on any migration, committed query or service that
-- reads the closure table directly outside the three files that are allowed to; and the
-- vocabulary a reader has available no longer contains the wrong query.
--
-- ── THE COLUMN LIST IS EXPLICIT, AND §5.4's `*` IS NOT COPIED VERBATIM ────────────────────────
--
-- §5.4 writes `SELECT DISTINCT ON (clause_uuid, as_of_commit) *`. CockroachDB expands `*` at view
-- creation time, so the two forms produce the same view TODAY — and diverge the moment a column
-- is added to 0038, at which point the `*` form silently keeps its old shape while the file that
-- created it appears to say otherwise. Writing the columns out makes the view's contract legible
-- in the file that defines it, and makes adding a column a two-file change that shows up in
-- review rather than a one-file change that does not.
--
-- It also keeps this view STATEMENT-FOR-STATEMENT ISOMORPHIC to
-- `packages/trappoint-sql/refvertical/sql/0039_clause_blame_current.sql`. That is not tidiness:
-- the reference vertical's `[[authority_source]].relation` names its `clause_blame_current`, and
-- a projection trigger rendered from one kernel template must read `max_severity`, `virulence`
-- and `closure_gen` off either relation by name and behave identically. A column list that
-- diverged here would make the reference binding prove a smaller machine than the one that ships.
--
-- ── WHAT THIS VIEW DELIBERATELY DOES NOT DO ──────────────────────────────────────────────────
--
-- It does not filter, rename, re-band, aggregate or add a column. It projects the closure
-- unchanged, one row per clause version, at its highest generation. Every temptation to do more
-- here — join `clause_version`, expand `ancestor_events` into rows, compute `ancestry_complete`
-- from `truncated` — puts derivation into the relation the gate reads, and a derivation in a view
-- is a derivation no `CHECK` can see and no trigger can enforce. Those belong in
-- `0152_v_blame_origin` and in the console's contract, both of which read THIS view.
--
-- ── `DISTINCT ON`, ON COCKROACHDB ────────────────────────────────────────────────────────────
--
-- `DISTINCT ON` is PostgreSQL-compatible syntax that CockroachDB supports, and the `ORDER BY`
-- prefix must match the `DISTINCT ON` list — hence `ORDER BY clause_uuid, as_of_commit,
-- closure_gen DESC` and not merely `ORDER BY closure_gen DESC`.
--
-- VERIFIED: this file was applied to a live CockroachDB CCL v26.2.5 on 2026-08-10, and the view
-- was measured returning exactly one row per clause version at the HIGHEST generation while the
-- superseded generation remained readable in the table beneath it. A point lookup through the
-- view on `(clause_uuid, as_of_commit)` plans as a REVERSE SCAN of the primary index with
-- `limit: 1` and no de-duplication node at all — the optimizer recognises that the `DISTINCT ON`
-- list is a primary-key prefix — so the discipline costs nothing on the path the projector takes.
--
-- If a later version refuses `DISTINCT ON` inside a view, the one-file remediation is the window
-- form
--
--     SELECT … FROM (SELECT …, row_number() OVER (PARTITION BY clause_uuid, as_of_commit
--                                                 ORDER BY closure_gen DESC) AS rn
--                      FROM mainline.clause_blame_closure) WHERE rn = 1
--
-- which is semantically identical and keeps the view NAME, which is the thing every other file
-- in the repository depends on.
--
-- ── A NOTE FOR ANYONE WRITING A QUERY AGAINST THIS VIEW ───────────────────────────────────────
--
-- A predicate on a column that is neither in the `DISTINCT ON` list nor functionally determined
-- by it — `ancestor_events @> ARRAY[…]`, `max_severity >= 4`, even `site_id = $1` — is applied
-- ABOVE the de-duplication and CANNOT be pushed below it, because pushing it below would change
-- the answer: it would surface a superseded generation that happens to satisfy the predicate when
-- the current one does not. That is the view working correctly, and it has a cost on the plan.
-- `verticals/mainline/db/queries/EXPLAIN-ASSERTIONS.md` states that cost precisely, records what
-- CI actually asserts, and writes out the accelerated two-stage form for the day the cost stops
-- being acceptable — together with what adopting it would require of DM-9.

CREATE VIEW mainline.clause_blame_current AS
SELECT DISTINCT ON (clause_uuid, as_of_commit)
       clause_uuid,
       as_of_commit,
       closure_gen,
       site_id,
       ancestor_events,
       ancestor_count,
       max_severity,
       virulence,
       depth,
       truncated,
       computed_by,
       projector_ver,
       computed_at
  FROM mainline.clause_blame_closure
 ORDER BY clause_uuid, as_of_commit, closure_gen DESC;
