-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0039_clause_blame_current.sql
-- CREATE VIEW trappoint_ref.clause_blame_current — the relation the binding actually names
--
-- MI: MI26
-- I: I05
-- COUNSEL-GATED: no
-- RATIONALE: HAND-WRITTEN, NOT RENDERED. `[[authority_source]].relation` in
--            refvertical/vertical.toml is `trappoint_ref.clause_blame_current`, not the
--            closure table. Without this file the reference binding declares an
--            authority relation that does not exist, and the Authority Source Contract
--            would be satisfied at render time by a name that no projection trigger
--            could ever read — which is the exact failure the contract exists to make
--            impossible. Isomorphic to ARCHITECTURE.md §5.4's
--            `mainline.clause_blame_current`, statement for statement.
--
-- NOT rendered from a template, and therefore carrying no rendered-by banner:
-- `trappoint render --check` leaves this file alone by design (it is domain content of
-- the reference vertical, not substrate), and `stem_collisions()` sees one file at
-- version `0039_clause_blame_current`.
--
-- WHY A VIEW RATHER THAN A QUERY AT EVERY CALL SITE.
--   `clause_blame_closure` is append-only and generation-versioned: recomputing a
--   closure writes a NEW `(clause_uuid, as_of_commit, closure_gen)` row and overwrites
--   nothing, which is what keeps last year's closure readable this year. The price is
--   that every reader owes the discipline `max(closure_gen)`, and a reader that forgets
--   it silently projects a SUPERSEDED severity onto a live blocking check. One view is
--   how that discipline stops being per-call-site.
--
--   The error direction is the reason this is not a stylistic preference: an older
--   generation is the generation computed with LESS ancestry, so forgetting the
--   discipline understates ancestral severity, and understating severity is the one
--   error direction with physical consequences.
--
-- `DISTINCT ON` is PostgreSQL-compatible syntax that CockroachDB supports, and the
-- `ORDER BY` prefix must match the `DISTINCT ON` list — verified against the local
-- v26.2.5 node by applying this file, not assumed from the manual.
--
-- The view is deliberately NOT a `SELECT *`-with-extra-columns: it projects the closure
-- unchanged. A projection trigger rendered from a kernel template reads
-- `max_severity`, `virulence` and `closure_gen` off this relation by name, exactly as it
-- reads them off `mainline.clause_blame_current`, and a column list that diverged here
-- would make the reference vertical prove a smaller machine than the one that ships.

CREATE VIEW trappoint_ref.clause_blame_current AS
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
  FROM trappoint_ref.clause_blame_closure
 ORDER BY clause_uuid, as_of_commit, closure_gen DESC;
