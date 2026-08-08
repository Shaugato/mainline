-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI16, MI25
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: `event_cue_coarse.severity_gate` decides whether a taxonomy-sweep hit blocks a permit — a sweep hit is never blocking unless `severity_gate = 5` — which makes it precisely the column an inserter must not be able to write, so it is projected from `mainline.event` through `event_cue.event_id` on every insert.
--
-- migration:  0114a_fn_cue_coarse_project
-- band:       0110-0114z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). The `a` suffix is
--             MR-5's band-overflow use: recall's function band ends at `0114` and `0115`
--             belongs to kernel `merge-gate-and-core`, so this domain suffixes its own last
--             number instead of borrowing a neighbour's. That is the mechanism that prevents
--             the 2026-08-08 incident from recurring.
-- domain:     recall
-- statements: 1
-- proposes:   MI31 — "the vector-index prefix columns are projections of the parent cue, never
--             inputs; a vector with no parent cue is refused" (see 0041, 0114)
-- source:     docs/leads/recall.md D1 · ARCHITECTURE.md §5.4 (S20), §5.11
-- requires:   0040 mainline.event_cue · 0033 mainline.event
-- provides:   mainline.fn_cue_coarse_project() — welded to mainline.event_cue_coarse by 0138a
-- companion:  0114_fn_cue_prefix_project.sql — the prefixed sidecar's projector, and the file
--             that carries PLATFORM NOTE 2 (why the mechanism is two functions, not one).
-- sqlstate:   P0001
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- ── WHY THIS FILE EXISTS (migration reconciliation, 2026-08-08) ───────────────────────────────
-- `fn_cue_coarse_project` was the second of two `CREATE FUNCTION` statements in
-- `0114_fn_cue_prefix_project.sql`. Two functions was always the right call and 0114's PLATFORM
-- NOTE 2 is why; two functions in ONE FILE was not, and the reason is the runner rather than
-- taste. The runner does not wrap a migration body in a transaction, because CockroachDB DDL is
-- not transactional across statements. A file that fails on its second statement therefore
-- leaves the schema half-applied with the version unrecorded, and `dirty` names a FILE, not a
-- STATEMENT — so the operator is told "0114 is dirty" and must diff the catalogue by hand to
-- learn which half landed.
--
-- Which half landed is not a detail here. The failure ordering that matters is exactly the one
-- the old file made possible: `fn_cue_prefix_project` created, `fn_cue_coarse_project` absent.
-- 0138a would then fail too, and the deployment would carry a welded prefixed sidecar and an
-- unwelded coarse one — the state in which a mis-taxonomised severity-5 event is retrievable by
-- the sweep and then not blocking, because `severity_gate` was whatever the inserter said.
--
-- ── ON THE COARSE SIDECAR ────────────────────────────────────────────────────────────────────
-- `event_cue_coarse` has one deliberately constant prefix (`tenant_id`), so its tree placement
-- is not forgeable — one big unpartitioned K-means tree is the point of the taxonomy-insurance
-- sweep. But its `severity_gate` IS forgeable, and that column decides whether a sweep hit
-- blocks: a sweep hit is never blocking unless `severity_gate = 5`. It is therefore projected
-- from `mainline.event` through `event_cue.event_id`.
--
-- `tenant_id` is left alone, and that gap is named rather than papered over: DM-3 makes
-- `mainline.site` its authoritative source, and forging a projection from a table this domain
-- does not own would be worse than naming the gap. Until that projection lands, `tenant_id` is a
-- client-supplied constant — recorded in 0042 as an unclosed weld rather than claimed as
-- enforced.
--
-- The RAISE is on the parent CUE, not on the event, and the message is deliberately the same
-- sentence 0114 raises: both functions are placing a vector, both refuse for the same reason —
-- there is no authoritative row to place it from — and an operator reading a log should not have
-- to know which sidecar failed to know what happened. `cue_sev` is NULL when the cue is missing
-- and also when the cue's event is missing, and both are the same defect: a vector with no
-- authoritative parent.
--
-- Style (§5.11): PL/pgSQL, row-level, no FOR..IN, no FOREACH, no EXECUTE, no PERFORM, no CASE;
-- IF plus exactly one SELECT..INTO.
--
-- PLATFORM: CockroachDB requires `OLD`/`NEW` to be parenthesised when a COLUMN is read —
-- `(NEW).cue_id`, not `NEW.cue_id` — a documented known limitation whose own v26.2 examples read
-- `(NEW).wage` and assign `NEW.wage := …`. The assignment target below is deliberately bare,
-- matching that example. See 0114's PLATFORM NOTE 1; it applies verbatim here.

CREATE FUNCTION mainline.fn_cue_coarse_project() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  cue_sev INT2;
BEGIN
  SELECT e.severity_gate
    INTO cue_sev
    FROM mainline.event_cue c
    JOIN mainline.event e ON e.event_id = c.event_id
   WHERE c.cue_id = (NEW).cue_id;

  IF cue_sev IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no parent cue — cannot place a vector in a prefix tree';
  END IF;

  NEW.severity_gate := cue_sev;
  RETURN NEW;
END $$;
