-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
--
-- MAINLINE · 0089_agent_action.sql
-- CREATE TABLE mainline_meas.agent_action — what the fleet did, one row per attempt
--
-- MI: MI01
-- I: I15
-- COUNSEL-GATED: no
-- RATIONALE: This table is the producer three audit views already select from by name, and
--            the shape is transcribed rather than designed: every column below is read by
--            0164, 0165 or 0166. The one design decision that is MINE to defend is what the
--            table refuses to carry — there is no `signer_sub`, no `actor_sub`, no person
--            key of any kind on the aggregation path, because `agent_role` maps 1:1 to the
--            SQL role that executed the action and a role is a MACHINE. 0164's header sets
--            this out in full under I15/SEC-3: `signer_sub` is a span attribute and NEVER a
--            metric label, "a dimension we cannot aggregate on is a dimension we cannot
--            accidentally publish". A grouping column that cannot reach a name cannot be
--            joined into a per-named-human distribution by a later view, however that view
--            is written. `subject_id` is present and nullable because the evidentiary link
--            from an action to the thing it acted on is what makes the row auditable at
--            all; it is a subject key, it is not indexed as a grouping dimension by any of
--            the three consumers, and it is the reason `by_subject` exists — point lookup
--            for one subject's history, not a scan that produces a distribution.
--
-- migration:  0089_agent_action
-- domain:     recall
-- band:       0080-0089z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). The number is
--             not chosen here: 0164, 0165 and 0166 each carry
--             `requires: 0089 mainline_meas.agent_action` in a header that was written
--             before this file existed, and ARCHITECTURE.md §18 places `agent_action` in
--             0080-0089. Choosing any other number would falsify three committed artefacts.
-- statements: 1
-- invariants: MI01 — evidentiary tables are append-only. THIS FILE DOES NOT MAKE THAT TRUE;
--                    0149a welds it with `BEFORE UPDATE OR DELETE ... fn_refuse_mutation`.
--                    Stated here because 0164's header already cites MI01 over this table,
--                    so a table landing without its weld lands with a published invariant
--                    already broken.
--             I15  — the allegation firewall. No column on this table characterises a named
--                    human; see the RATIONALE and 0164's I15/SEC-3 block.
-- source:     ARCHITECTURE.md §5.7 (verbatim DDL, the block at line 1517) · §11.5 (SEC-3,
--             the A-RULE and the Attribution Rule) · §12 (Class A vs Class B telemetry) ·
--             §16 (40001 is the only retryable code) · §17 (the three consuming views) ·
--             §18 (band placement) · spec/invariants/I15-allegation-firewall.md
-- requires:   0002 CREATE SCHEMA mainline_meas
-- sqlstate:   23514 on a CHECK violation — an unmodelled `transport`, an unmodelled
--             `outcome`, an empty `agent_role` or `tool`, a digest that is not 32 bytes, or
--             a negative `latency_ms`. This object raises nothing itself.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14), and no .up.sql
--             either (MR-5).
--
-- ─────────────────────────────────────────────────────────────────────────────
-- EVERY COLUMN IS READ BY A CONSUMER THAT ALREADY EXISTS
-- ─────────────────────────────────────────────────────────────────────────────
-- 0164 v_agent_actions        agent_role, tool, outcome, at, transport, sqlstate,
--                             model_id, prompt_version, latency_ms
-- 0165 v_gate_latency_daily   at, tool, outcome, latency_ms, and the two-predicate
--                             filter `agent_role = 'agent_gate' AND transport = 'pgwire'`
-- 0166 v_txn_restart_daily    at, agent_role, sqlstate
--
-- The columns no consumer reads — `action_id`, `subject_kind`, `subject_id`,
-- `input_sha256`, `output_sha256`, `granted_scopes` — are the evidentiary payload, and
-- 0164's closing paragraph says exactly why they are off that surface: two 32-byte digests
-- per row would blow the 10 KiB cap at about forty rows. They are on the TABLE because the
-- view is a summary and the row is the record.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY `latency_ms` IS INT4 AND STAYS INT4
-- ─────────────────────────────────────────────────────────────────────────────
-- 0165 computes `round(avg(a.latency_ms)::NUMERIC, 1)`. On CockroachDB v26.2.5 `avg()` over
-- an integer returns DECIMAL, the cast is a no-op that documents intent, and `round(…, 1)`
-- is the two-argument DECIMAL form. Widening this column to FLOAT8 to suit a mental model
-- would silently change that call to the one-argument FLOAT8 `round()` — which takes no
-- precision argument — and the view would stop applying. The consumer is older than this
-- file; the column serves it.
--
-- NULL is meaningful and is not zero. `unmeasured` in 0165 counts exactly
-- `latency_ms IS NULL`, and `measurement_complete` is false for any day+tool group that
-- contains one. An action nobody timed must therefore be recorded as untimed, never as
-- instantaneous — a default of 0 would turn a gap in instrumentation into a good number.
-- `CHECK (latency_ms IS NULL OR latency_ms >= 0)` admits the null and refuses the absurd.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY `sqlstate` CARRIES NO CHECK, DELIBERATELY
-- ─────────────────────────────────────────────────────────────────────────────
-- This is the one place where the fail-closed reading argues AGAINST a constraint. §16
-- models five refusal codes (`40001`, `23514`, `23503`, `23505`, `P0001`) and 0166 breaks
-- out a sixth (`42501`, the S22 missing-write-policy signature). Constraining the column to
-- that set would mean the database REFUSED TO RECORD any refusal nobody had modelled — and
-- `unmodelled_refusals` (0164) and `unmodelled` (0166) are the two most actionable numbers
-- on the whole audit surface. A constraint here would guarantee they read zero forever, by
-- construction, which is the exact shape of a metric that lies. The column is open, the
-- views classify, and an unmodelled code arrives as evidence instead of as a lost write.
--
-- NULL means "no SQLSTATE was returned", which is the normal case for `outcome = 'ok'`.
-- Both counting views test `sqlstate IS NOT NULL` before classifying, so a null is never
-- counted as an unmodelled refusal.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- THE DIGEST COLUMNS AND WHY THEIR LENGTH IS CHECKED
-- ─────────────────────────────────────────────────────────────────────────────
-- `input_sha256` / `output_sha256` are BYTES and NOT NULL, so every action carries the pair
-- that lets a replay be compared against what was actually sent and returned. A BYTES column
-- accepts any length, and a 20-byte value in a column named sha256 is a digest from another
-- algorithm wearing this one's name; `length(...) = 32` is the house check on digest columns
-- and it is applied here for that reason. It constrains the SHAPE of the evidence and says
-- nothing about its content — this is not a claim that the digest is correct, only that it
-- is a SHA-256-sized thing.
--
-- `granted_scopes STRING[] NOT NULL` records the authority the action ran under, per row,
-- at the time it ran. An empty array is legal and means an action ran with no scope granted;
-- that is a finding, not a data error, and refusing it here would delete the evidence of it.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- KEY AND INDEXES
-- ─────────────────────────────────────────────────────────────────────────────
-- `gen_random_uuid()` for the primary key. Sequences, SERIAL and `unique_rowid()` are banned
-- tree-wide (`trappoint migrate lint` refuses them by regex): a gap in a sequence is
-- ambiguous, and this is a ledger where a gap has to MEAN something.
--
-- `by_role_time (agent_role, at DESC)` serves 0165's role filter and 0166's per-role daily
-- grouping; `by_subject (subject_id, at DESC)` serves one subject's history. Both are
-- declared inline so that the table and its access paths are one statement — CockroachDB
-- DDL is not transactional across statements, and a separate CREATE INDEX file is a file
-- that can fail on its own and leave the table half-welded.

CREATE TABLE mainline_meas.agent_action (
  action_id      UUID NOT NULL DEFAULT gen_random_uuid(),
  agent_role     STRING NOT NULL,               -- maps 1:1 to the SQL role that executed it
  tool           STRING NOT NULL,
  transport      STRING NOT NULL,
  model_id       STRING NULL,
  prompt_version STRING NULL,
  subject_kind   STRING NULL,
  subject_id     UUID NULL,
  input_sha256   BYTES NOT NULL,
  output_sha256  BYTES NOT NULL,
  granted_scopes STRING[] NOT NULL,
  outcome        STRING NOT NULL,
  sqlstate       STRING NULL,                   -- OPEN by design; see the header
  latency_ms     INT4 NULL,                     -- NULL means untimed, never zero
  at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT agent_action_pk PRIMARY KEY (action_id),
  CONSTRAINT agent_action_transport_known CHECK (
    transport IN ('pgwire', 'mcp', 'bedrock', 'ccloud', 's3')),
  CONSTRAINT agent_action_outcome_known CHECK (
    outcome IN ('ok', 'refused', 'error', 'abstained')),
  CONSTRAINT agent_action_role_present CHECK (agent_role <> ''),
  CONSTRAINT agent_action_tool_present CHECK (tool <> ''),
  CONSTRAINT agent_action_input_digest_len CHECK (length(input_sha256) = 32),
  CONSTRAINT agent_action_output_digest_len CHECK (length(output_sha256) = 32),
  CONSTRAINT agent_action_latency_nonnegative CHECK (
    latency_ms IS NULL OR latency_ms >= 0),
  INDEX by_role_time (agent_role, at DESC),
  INDEX by_subject (subject_id, at DESC)
);
