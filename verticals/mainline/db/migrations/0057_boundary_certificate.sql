-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI06, MI01
-- I: I06, I01
-- COUNSEL-GATED: no
-- RATIONALE: Finding S11 — `boundary_complete_when_issued` failed OPEN in a fail-closed system. An asset with no modelled energy edges is UNKNOWN, not SAFE, and unknown must BLOCK. This table is the arithmetic that makes that true: `unmodelled_total = tags_unmodelled + under_declared` is computed by the server, projected onto `mainline.permit.unmodelled_asset_count`, and refused there by the plain-column CHECK `boundary_certified_when_issued`. An incomplete asset graph therefore produces a REFUSAL and not a silent pass.
--
-- migration:  0057_boundary_certificate
-- band:       0054-0057z · datamodel/ex-dm-gate · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.5 (shape, with two corrections argued below) · finding S11 ·
--             §16 MI06, MI01 · §6.5 the merge-gate certificate existence check
-- requires:   0050 mainline.permit (RENDERED). 0054-0056 are the INPUTS to this arithmetic and
--             are not referenced by it: a certificate is a statement about a computation, and
--             pointing it at the rows it counted would make deleting one of them a way to change
--             a signed count.
-- projects:   nothing. AUTHORITATIVE SOURCE for `mainline.permit.unmodelled_asset_count`, which
--             `fn_boundary_project` (band 0140-0149z) copies from `unmodelled_total` on the
--             HIGHEST `cert_gen` for the permit and RAISEs P0001 when no certificate exists.
-- sqlstate:   23503 on fk_certificate_permit; 23514 on counts_sane / declared_accounted_for /
--             cert_gen_positive / asset_graph_version_stated; 23505 on the primary key;
--             P0001 from the append-only trigger and from `fn_boundary_project` on a missing
--             certificate
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- CORRECTION 1 · §5.5 GIVES THIS TABLE `permit_id UUID NOT NULL PRIMARY KEY`, AND §6 LISTS IT
-- AMONG THE APPEND-ONLY TABLES (`fn_refuse_mutation`, MI01). THOSE TWO CANNOT BOTH HOLD.
--
-- One row per permit plus no UPDATE means the certificate can be computed exactly once, ever. But
-- a boundary is recomputed as a matter of course: the crew adds an isolation point, the site
-- loads a missing energy edge, a superseded tag is modelled. Under the literal §5 shape the
-- second computation is a 23505 and the first is unamendable, so the only way to record the new
-- arithmetic is to DELETE the evidence of the old — which is the one operation this substrate
-- exists to refuse.
--
-- Resolved in favour of APPEND-ONLY, because MI01 names this table explicitly and because the
-- product's whole idiom is that a superseding fact is a NEW ROW and never an overwrite. The shape
-- is the one `clause_blame_closure` already uses for the same problem (DM-9): generation-
-- versioned, append-only, highest generation wins.
--
--   PRIMARY KEY (permit_id, cert_gen)      cert_gen 1, 2, 3 … per permit
--   the reader takes max(cert_gen)         exactly as the closure reader takes max(closure_gen)
--
-- `cert_gen` IS DERIVED IN-TRANSACTION AS `1 + coalesce(max(cert_gen), 0)` FOR THE PERMIT — never
-- from a sequence. `CREATE SEQUENCE`, `nextval`, `SERIAL` and `unique_rowid()` are banned tree-
-- wide (ruling D10, enforced by `trappoint migrate lint`) and the reason applies here in full: a
-- sequence may leave gaps, so under a sequence a missing generation means nothing. Derived by
-- CAS under SERIALIZABLE, a gap in this column MEANS a certificate was destroyed.
--
-- WHAT THIS COSTS A READER, STATED PLAINLY: `SELECT … WHERE permit_id = $1` now returns a history
-- rather than a row, and any reader that wants "the certificate" must order by `cert_gen DESC
-- LIMIT 1`. The merge gate's existence check (§6.5, `NOT EXISTS (SELECT 1 FROM
-- boundary_certificate WHERE permit_id = …)`) is unaffected and needs no edit.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- CORRECTION 2 · §5.5's `counts_sane` IS VACUOUS, AND ITS OMISSION IS THE S11 BUG AGAIN.
--
--   CONSTRAINT counts_sane CHECK (tags_resolved + tags_unmodelled >= 0 AND tags_declared >= 0)
--
-- `under_declared` is not mentioned. It is also the column that ACCUSES — assets in the energy
-- closure that the boundary never declared, the trapped-hydraulic term in the canonical
-- multi-source fatality. And the projected quantity is a SUM:
--
--   unmodelled_asset_count = tags_unmodelled + under_declared
--
-- So `under_declared = -3` with `tags_unmodelled = 3` projects ZERO, `boundary_certified_when_
-- issued` passes, and a permit with three unmodelled assets merges. The refusal is not defeated
-- by an attack on the gate; it is defeated by arithmetic on an unconstrained integer, which is
-- the same fail-open direction S11 was raised about. Every one of the four counts is therefore
-- constrained non-negative here, and the sum is computed by the SERVER (`unmodelled_total`)
-- rather than by whoever writes the projection, so the gate and the certificate cannot come to
-- disagree about the formula.
--
-- `declared_accounted_for` — every DECLARED tag is either resolved (it has edges, so it is
-- reachable from itself) or unmodelled (it has none). There is no third case, so
-- `tags_resolved + tags_unmodelled >= tags_declared` must hold for any honest computation. It is
-- `>=` and not `=` because both terms legitimately count tags that were never declared:
-- `tags_resolved` includes closure members reached from a declared tag, and `tags_unmodelled`
-- counts adjacent tags as well as declared ones. A certificate that fails this arithmetic is a
-- computation that lost tags, and losing tags is under-counting, which is the direction that
-- kills people.
--
-- `asset_graph_version` IS THE RE-CHECKABILITY HOOK and it is refused blank. The certificate's
-- claim is "under graph version V, this boundary had these gaps"; a certificate whose V is the
-- empty string cannot be re-run against the graph it was computed over, and an exhibit that
-- cannot be re-derived is a number somebody typed. NOT NULL does not close that — '' satisfies it.
--
-- WHY THIS TABLE TAKES NO FOREIGN KEY ONTO `asset_edge`, `permit_boundary` OR `permit_slice`.
-- A certificate is a frozen statement about a computation at a moment. Binding it to the rows it
-- counted would mean the counted rows could not change without either cascading (forbidden — a
-- cascade rewrites history) or blocking legitimate maintenance of the asset graph. The correct
-- reading of an old certificate is "this was true of graph version V", and V is recorded.
--
-- VERIFIED 2026-08-10 against CockroachDB CCL v26.2.5 (local single node, insecure, 26257). All
-- four corrections hold as measured behaviour, not as intentions:
--
--   * the statement applies, generated column included;
--   * `under_declared = -3` is refused with SQLSTATE 23514 and the server names `counts_sane`;
--   * `tags_declared = 9` against `tags_resolved + tags_unmodelled = 4` is refused naming
--     `declared_accounted_for`;
--   * `unmodelled_total` reads back as `tags_unmodelled + under_declared`, and an INSERT that
--     supplies a value for it is REFUSED — the client cannot write a zero beside non-zero
--     components;
--   * cert_gen 1 and cert_gen 2 for one permit COEXIST, and a repeated (permit_id, cert_gen) is
--     23505 — the append-only recomputation this file argues for actually works;
--   * a blank `asset_graph_version` is refused naming `asset_graph_version_stated`.
--
-- Evidence: tests/integration/schema/test_mi_boundary_override.py, the certificate cases.

CREATE TABLE mainline.boundary_certificate (
  permit_id           UUID   NOT NULL,
  -- 1, 2, 3 … per permit. Derived in-transaction as 1 + coalesce(max(cert_gen), 0). NEVER a
  -- sequence: under CAS a gap in this column MEANS a certificate was destroyed.
  cert_gen            INT8   NOT NULL,
  asset_graph_version STRING NOT NULL,
  tags_declared       INT4   NOT NULL,   -- rows in permit_boundary for this permit
  tags_resolved       INT4   NOT NULL,   -- reachable in asset_edge from a declared tag
  tags_unmodelled     INT4   NOT NULL,   -- declared or adjacent, with NO edges at all
  under_declared      INT4   NOT NULL,   -- in the energy closure, ABSENT from the boundary
  -- The gate's number, computed by the SERVER. `fn_boundary_project` copies THIS column onto
  -- mainline.permit.unmodelled_asset_count; it does not re-derive the sum. One formula, one
  -- place, and no way for the certificate and the gate to disagree about what blocks.
  unmodelled_total    INT4   AS (tags_unmodelled + under_declared) STORED,
  computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT boundary_certificate_pk PRIMARY KEY (permit_id, cert_gen),
  CONSTRAINT fk_certificate_permit FOREIGN KEY (permit_id)
    REFERENCES mainline.permit (permit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT cert_gen_positive CHECK (cert_gen >= 1),
  -- All FOUR counts. §5.5 omitted under_declared, and the sum is what the gate reads.
  CONSTRAINT counts_sane CHECK (tags_declared >= 0
                            AND tags_resolved >= 0
                            AND tags_unmodelled >= 0
                            AND under_declared >= 0),
  CONSTRAINT declared_accounted_for
    CHECK (tags_resolved + tags_unmodelled >= tags_declared),
  CONSTRAINT asset_graph_version_stated CHECK (asset_graph_version <> '')
);
