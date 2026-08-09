-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0066a_one_live_disposition.sql
-- CREATE UNIQUE INDEX one_live_disposition — at most one live clearance per obligation
--
-- MI: MI08
-- I: I09
-- COUNSEL-GATED: yes
-- RATIONALE: MI08 as a partial unique index rather than a trigger. Two live dispositions
--            against one obligation is how a retracted clearance and its replacement become
--            indistinguishable, and how a second signer quietly overwrites the first one
--            refusal. The predicate is retracted_by IS NULL, so the history stays in the
--            table forever and only the live row is constrained.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0066_disposition.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- PARTIAL, AND THE PREDICATE IS THE POINT. A plain `UNIQUE (check_id)` would forbid the
-- retraction-and-replacement sequence entirely, which is the ordinary lifecycle: a
-- mechanism_absent verdict is revoked when its predicate falsifies, the check re-opens,
-- and a new disposition is signed. `WHERE retracted_by IS NULL` lets the retracted row
-- stay in the table forever — it is evidence — while constraining the one row that
-- currently clears the obligation.
--
-- 23505 NAMING `one_live_disposition` IS THE PUBLISHED CONTRACT (case CF-12). The index
-- name is the exhibit, so it is written here rather than left to CockroachDB's
-- auto-naming, and it must not be renamed without a MAJOR specification bump.
--
-- GT: partial UNIQUE indexes are measured PASS on v26.2.5 (ADR 0002 F3), which is
-- what makes this one implementable as an index rather than as a counting trigger. A
-- trigger would be a second mechanism to disable; an index is a physical impossibility.

CREATE UNIQUE INDEX one_live_disposition
  ON trappoint_ref.disposition (check_id)
  WHERE retracted_by IS NULL;
