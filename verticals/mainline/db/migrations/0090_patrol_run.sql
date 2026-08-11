-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
--
-- MAINLINE · 0090_patrol_run.sql
-- CREATE TABLE mainline.patrol_run — the stated denominator that turns "the patrol found
-- nothing" into a bounded claim about how much of the plant was actually looked at
--
-- MI: MI21, MI22
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: A coverage claim with an unstated denominator is not a coverage claim. This
--            table exists so that `n_not_checked / n_in_scope` has a row behind it, and so
--            that `finished_at IS NULL` — a patrol that started and never came back — is a
--            representable, readable state rather than an absence indistinguishable from a
--            patrol that never ran. 0163_v_fixity_coverage is the reader; its
--            `not_checked_ratio` is the only number on the audit surface that reports what
--            the system DID NOT DO, and it has had no producer since the view was written.
--
-- migration:  0090_patrol_run
-- domain:     datamodel / dm-periphery
-- band:       0090-0099z · datamodel/dm-periphery · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), whose declared
--             contents for this band are "fixity, fleet, governance, frontier, contradiction
--             pair, mainline_ops.*". `patrol_run` is the fixity head of that list.
-- statements: 1
-- invariants: MI21 — an UNDETERMINED fixity result never blocks. The corollary this table
--                    carries is the one 0163 reports: an unchecked asset is not a passed
--                    asset, so the count of what was NOT checked is a first-class column and
--                    not a subtraction somebody performs later.
--             MI22 — the gate fails closed on a stale or absent projection. `started_at`,
--                    `finished_at` and `as_of_hlc` are what make a stale patrol legible AS
--                    stale: a run with no `finished_at` is unfinished, and `as_of_hlc` says
--                    which instant of the database the scan actually saw.
--             I06  — a dependency a gate consumes is COMPUTED, never declared. Coverage is
--                    computed from these counts; nobody declares that a site is covered.
-- source:     hackathon-research/ARCHITECTURE.md §5.8 line 1629 — transcribed column for
--             column, type for type, key for key · §17 (v_fixity_coverage) · §11.7 (no live
--             OT claim: observations arrive by export, which is why `as_of_hlc` is a
--             follower-read timestamp and not a plant clock)
-- requires:   0001a CREATE SCHEMA mainline (RENDERED; template 0001_schemas.sql.j2)
-- provides:   mainline.patrol_run — read by 0163_v_fixity_coverage
-- sqlstate:   23505 on `patrol_run_occurrence_unique` — the at-least-once redelivery case,
--             and the producer's expected path (see below). 23514 on the four named CHECKs:
--             `patrol_run_class_known`, `patrol_run_counts_nonneg`,
--             `patrol_run_account_within_scope` and `patrol_run_finished_after_started`.
--             This table gates nothing.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- THE UNIQUE KEY IS LOAD-BEARING, AND IT IS LOAD-BEARING FOR ONE NAMED REASON
-- ─────────────────────────────────────────────────────────────────────────────
-- §5.8 writes the constraint with its reason attached — "EventBridge Scheduler
-- is at-least-once" — and that is not a footnote. AWS EventBridge Scheduler
-- guarantees at-least-once invocation, so the same occurrence of the same
-- schedule WILL be delivered twice under retry, and a patrol that recorded two
-- runs for one occurrence would double both the numerator and the denominator of
-- every coverage number computed from it.
--
-- The producer does not merely tolerate that; it depends on this key BY NAME.
-- verticals/mainline/packages/mainline-fixity/.../emit.py::INSERT_PATROL_RUN_SQL
-- ends
--
--     ON CONFLICT (site_id, schedule_id, occurrence_ts) DO NOTHING
--     RETURNING run_id
--
-- and `insert_patrol_run` documents the empty result as THE SUCCESS CASE for a
-- redelivery. `ON CONFLICT` requires an arbiter — a unique index over exactly
-- those three columns — so dropping or reshaping this constraint does not degrade
-- de-duplication, it makes the producer's only insert statement fail to plan.
-- That is why the constraint is declared here rather than left to a later index.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY `<=` AND NOT `=`, AND WHAT WAS MEASURED BEFORE CHOOSING
-- ─────────────────────────────────────────────────────────────────────────────
-- §5.8 states no arithmetic constraint at all. The producer states a stronger one
-- than this file does, and the difference is deliberate.
--
-- MEASURED, by reading the only writer in the repository:
--
--   * `PatrolAccount.balanced()` (mainline_fixity/types.py) is
--     `n_in_scope == n_checked + n_not_checked`, EXACTLY;
--   * `PatrolRun.__post_init__` raises `PatrolAccountUnbalanced` — "patrol
--     accounting does not close" — on any account that fails it, so an unbalanced
--     run never reaches a `Statement`;
--   * `PatrolAccount.__post_init__` refuses a negative count outright;
--   * tests/unit/fixity/test_patrol.py exercises the refusal with
--     `PatrolAccount(n_in_scope=10, n_checked=3, n_not_checked=3)`.
--
-- So equality holds for every row this deployment's producer can emit, and `<=`
-- is implied by it: the CHECK below is satisfied by construction, not by hope.
--
-- Equality is NOT written into the schema, because the schema admits a shape the
-- producer does not. `finished_at` is nullable in §5.8 and 0163 counts
-- `unfinished_runs` from it — a run that started and never finished. A two-phase
-- writer holding UPDATE (the fleet's own scheduler, a future recovery path) would
-- open such a row with its accounting incomplete, and an equality CHECK would
-- refuse the very state the nullable column and the view were written to report.
-- `<=` admits the in-flight row and still bounds the consumer's quotient at 1.0,
-- which is the property 0163 actually needs:
--
--     round(sum(n_not_checked)::NUMERIC / nullif(sum(n_in_scope), 0)::NUMERIC, 4)
--
-- A coverage ratio above 1.0 would be a report that more assets went unchecked
-- than were ever in scope, and there is no reading of that number a reviewer can
-- act on.
--
-- Note what the nullable `n_in_scope = 0` case does NOT do: it does not become
-- 0.0. `nullif` sends it to NULL, and 0163's header spends a section on why that
-- distinction matters. Nothing here coalesces it, and nothing here should.
--
-- `patrol_run_finished_after_started` is chosen on the same evidence and admits
-- the same shape: `PatrolRun.__post_init__` already raises `UnstartedPatrol` when
-- `finished_at < started_at`, and the CHECK is written to pass on a NULL
-- `finished_at` rather than to require one, so it constrains the closed run and
-- says nothing about the open one. 0163 reads `max(finished_at)` as
-- `last_completed`, and a completion timestamp that precedes its own start makes
-- that column report a staleness that never happened.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- NO ROW-LEVEL TTL, AND NO APPEND-ONLY WELD EITHER
-- ─────────────────────────────────────────────────────────────────────────────
-- §4.1 law 13: zero row-level TTL in schema `mainline`, forever, and
-- test_mi_foundation.py::test_no_row_level_ttl_anywhere_in_schema_mainline reads
-- `SHOW CREATE` back to assert it. A patrol run is the record of an inspection
-- that did or did not happen, which is precisely the class of document the Crimes
-- (Document Destruction) Act 2006 (Vic) is about.
--
-- The append-only weld is a separate question and the answer is that it belongs
-- to the grant matrix here, not to a trigger. GRANTS.yaml gives `agent_patroller`
-- exactly `INSERT` on this table (since: "0090") and no UPDATE and no DELETE, and
-- mainline_fixity's docstring draws the consequence explicitly: an in-flight run
-- is unrepresentable under that role, a patrol that crashes writes no row at all,
-- the occurrence is therefore never marked done, and at-least-once redelivery
-- re-runs it. That behaviour falls out of the privilege rather than out of a
-- retry policy, and a refusal trigger would add nothing a role without UPDATE
-- does not already have.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS TABLE IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. IT IS NOT LIVE OT DATA, and §11.7 forbids claiming that it is. `as_of_hlc`
--    is the follower-read timestamp the scan used against OUR OWN record of
--    observed assertions. The observations arrive by export; this column says
--    which version of our record was consulted, not what the plant was doing.
-- 2. IT IS NOT THE FINDINGS. What a patrol found is `mainline.drift_finding`,
--    typed by `fixity_class` and carrying a DERIVED `gate_class`. This table says
--    how much was looked at. Conflating the two is how a clean patrol over
--    eleven per cent of a site gets reported as a clean site.
-- 3. IT IS NOT A SCHEDULE. `schedule_id` and `occurrence_ts` name the occurrence
--    the run answers, so that a missed occurrence is discoverable by its absence;
--    the schedule itself lives in EventBridge and is a deployment concern.

CREATE TABLE mainline.patrol_run (
  run_id        UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_id       UUID        NOT NULL,
  patrol_class  STRING      NOT NULL,
  -- The occurrence this run answers. STRING rather than a foreign key: the schedule lives
  -- in EventBridge, outside this database, and a foreign key into a system we do not
  -- administer would be a claim we cannot enforce.
  schedule_id   STRING      NOT NULL,
  occurrence_ts TIMESTAMPTZ NOT NULL,
  -- The scope predicate as evaluated, stored beside its own result. A denominator whose
  -- definition is not recorded beside it is a denominator nobody can re-derive.
  scope_pred    JSONB       NOT NULL,
  n_in_scope    INT8        NOT NULL,
  n_checked     INT8        NOT NULL,
  n_not_checked INT8        NOT NULL,
  -- The follower-read timestamp the scan used, so every finding in a run describes the
  -- same instant of our record (§5.8). DECIMAL because that is what CockroachDB's
  -- cluster_logical_timestamp() returns; a run that cannot say when it looked has
  -- witnessed nothing.
  as_of_hlc     DECIMAL     NOT NULL,
  started_at    TIMESTAMPTZ NOT NULL,
  -- NULL means started and never finished. 0163 counts these as `unfinished_runs` and
  -- reports `coverage_complete = false` for the whole class while any one of them stands.
  finished_at   TIMESTAMPTZ NULL,

  CONSTRAINT pk_patrol_run PRIMARY KEY (run_id),
  -- EventBridge Scheduler is at-least-once. See the header: the producer's ON CONFLICT
  -- arbiter is exactly these three columns.
  CONSTRAINT patrol_run_occurrence_unique UNIQUE (site_id, schedule_id, occurrence_ts),
  CONSTRAINT patrol_run_class_known CHECK (patrol_class IN ('L0', 'L1', 'L2')),
  CONSTRAINT patrol_run_counts_nonneg
    CHECK (n_in_scope >= 0 AND n_checked >= 0 AND n_not_checked >= 0),
  CONSTRAINT patrol_run_account_within_scope
    CHECK (n_checked + n_not_checked <= n_in_scope),
  CONSTRAINT patrol_run_finished_after_started
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);
