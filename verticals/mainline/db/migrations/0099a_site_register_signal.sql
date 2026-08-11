-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
--
-- MAINLINE · 0099a_site_register_signal.sql
-- CREATE TABLE mainline_ops.site_register_signal — the mechanism-predicate watch source
--
-- MI: MI22
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: A `mechanism_absent` disposition binds a machine-checkable predicate over the
--            site's own registers — "this site operates no vessel in hazard class X" — and
--            the whole value of that construction is that it can be FALSIFIED without a
--            human deciding to look. This table is where a register change becomes an event
--            a changefeed can see. Without it the predicate is prose again, the revocation
--            never fires, and the exhibit goes back to "he signed it away and a man died".
--
-- migration:  0099a_site_register_signal
-- domain:     datamodel / dm-periphery
-- band:       0090-0099z · datamodel/dm-periphery · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), whose declared
--             contents for this band end with "mainline_ops.*". ARCHITECTURE.md §18 places
--             this table at 0099 beside the outbox; it takes the `a` suffix because MR-5
--             permits one top-level statement per file and 0099 is the outbox's.
-- statements: 1
-- invariants: MI22 — the gate fails closed on a stale or absent projection. A revocation that
--                    never fires is a projection that never updates: the disposition stays
--                    live, the check stays closed, and every gate reading it is reading a
--                    fact that stopped being true.
--             I06  — a dependency a gate consumes is COMPUTED, never declared. A predicate
--                    over the registers is computed from rows like these; nobody declares
--                    that a mechanism is absent and has it believed.
-- source:     hackathon-research/ARCHITECTURE.md §5.9 line 1266 — transcribed column for
--             column, including the source's own inline note "single family, no RLS: the CDC
--             watch source" · §5.9 (M8, falsifiable mechanism_absent) ·
--             verticals/mainline/db/RLS-MATRIX.yaml `rls_forbidden`
-- requires:   0005 CREATE SCHEMA mainline_ops (RENDERED; template 0001_schemas.sql.j2)
-- provides:   mainline_ops.site_register_signal — named by RLS-MATRIX.yaml `rls_forbidden`
--             and asserted by tests/integration/schema/test_mi_rls.py and
--             tests/integration/schema/test_ops_producer.py
-- sqlstate:   23514 on `site_register_signal_op_known`. This table gates nothing.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS TABLE BLOCKS TODAY, AND WHAT IT WILL CARRY TOMORROW
-- ─────────────────────────────────────────────────────────────────────────────
-- It blocks no migration. It is authored now because it blocks a NEGATIVE
-- ASSERTION, and a negative assertion that cannot run is worth nothing:
-- RLS-MATRIX.yaml lists exactly two tables under `rls_forbidden`, and
-- test_mi_rls.py parametrises over that list. Against a cluster where the second
-- table does not exist, the case does not report "no RLS here"; it fails on
-- `{table} does not exist`, which is a different sentence entirely and one that
-- says nothing about row-level security.
--
-- The mechanism it serves is §5.9's. `mainline.mechanism_predicate` (0065) carries
-- `registers STRING[]` — the WATCH SET, the register tables that can falsify the
-- predicate — and `0065a_predicate_watch_set_index` indexes it. A changefeed over
-- this table matches an incoming `(site_id, register, key, op)` against those
-- watch sets; when the predicate falsifies, `mainline.predicate_revocation`
-- (0065b) records what falsified it and when, the disposition is revoked, the
-- check re-opens and `gate_epoch` bumps. **The revocation is timestamped before
-- whatever happens next**, which is the entire point: not "he signed it away and a
-- man died", but "he signed under a lease the firm could call; it called
-- automatically at 04:12 on the 9th, before anything happened; here is the
-- transition and the three permits it re-blocked."
--
-- ─────────────────────────────────────────────────────────────────────────────
-- THE SAME THREE PLATFORM CONSTRAINTS AS THE OUTBOX, FOR THE SAME REASONS
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. SINGLE FAMILY. No `FAMILY` clause, and never one: CDC queries fail on
--    multi-family tables. §5.9 says so on the CREATE TABLE line itself.
-- 2. NO ROW-LEVEL SECURITY. CDC queries are not supported on RLS-enabled tables
--    and fail; CDC messages are not filtered by RLS in any case. Enabling it here
--    would hide nothing from an attacker and would stop the revocation. 0198x
--    carries the argument in full and this file's absence of a policy is the
--    other half of it.
-- 3. NO ROW-LEVEL TTL, AND THIS IS WHERE IT DIFFERS FROM THE OUTBOX. §5.9 states
--    no TTL and none is added. The TTL allowlist has exactly three entries and
--    this table is not one of them; a register change is the evidence that a
--    predicate stopped holding, and the date it stopped holding is the fact the
--    revocation is timestamped against.
--
-- No append-only weld either, and here the reasoning is the outbox's rather than
-- `agent_action`'s: this is a Class A transport (§12), the durable record of a
-- revocation is `mainline.predicate_revocation`, and the writer is the register
-- sync rather than an application role that could be granted DELETE by accident.

CREATE TABLE mainline_ops.site_register_signal (
  signal_id  UUID        NOT NULL DEFAULT gen_random_uuid(),
  -- Denormalised for the same reason the outbox's is: a CDC query permits no joins, so a
  -- consumer matching this signal against a predicate's watch set must be able to do it
  -- from the row alone.
  site_id    UUID        NOT NULL,
  -- Which register moved, and which entry in it. `register` is matched against
  -- mechanism_predicate.registers — the watch set — so it is the join key of a join that
  -- happens outside the database.
  register   STRING      NOT NULL,
  key        STRING      NOT NULL,
  op         STRING      NOT NULL,
  -- POINTERS AND DIGESTS ONLY, on the outbox's reasoning: a changefeed bypasses row-level
  -- security entirely and this table has no policy by construction.
  payload    JSONB       NOT NULL,
  emitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT pk_site_register_signal PRIMARY KEY (signal_id),
  -- Three operations and no more. A predicate over a register set is falsified by an
  -- addition, a removal or a change; a fourth verb would be a fourth falsification rule
  -- that nobody wrote, evaluated silently as "no match" by every consumer.
  CONSTRAINT site_register_signal_op_known CHECK (op IN ('add', 'remove', 'change'))
);
