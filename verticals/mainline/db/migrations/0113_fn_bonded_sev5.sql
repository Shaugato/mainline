-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0113_fn_bonded_sev5
-- domain:     recall
-- statements: 1
-- invariants: MI16 — every severity-5 event bonded to the permit's activity node or an ancestor
--             is blocking. This function is the half of MI16 the database maintains; the CHECK
--             `bonded_fatalities_all_blocking` (0081) is the half that refuses.
-- source:     ARCHITECTURE.md §5.11 ("fn_bonded_sev5 (blocking_check → recall_run
--             .n_bonded_sev5_blocking, S10)") · §5.7 · docs/leads/recall.md D2
-- requires:   0046 event_bond · 0058 blocking_check · 0081 recall_run
-- sqlstate:   23514 (raised BY THE CHECK, not by this function — see below)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- WHY THIS IS A TRIGGER AND NOT AN AGENT RESPONSIBILITY. MI16 is a POSITIVE invariant: it
-- asserts that something MUST be present. Negative invariants can be enforced by refusing a
-- write; positive ones cannot, because the offending write is the one that never happens. The
-- only way to make "every bonded fatality is blocking" refusable is to hold both sides of the
-- equation in columns and let a CHECK compare them — and then to make certain that neither side
-- is ever written by the party with the incentive. Hence: the blocking side is incremented here,
-- from `event_bond` ⋈ `event`, and the recognised side moves with it (RD-1, see 0081). An agent
-- that opens a run declaring a bonded fatality it did not materialise as a check is refused with
-- 23514 at INSERT time. An agent that materialises the check gets both counters moved for it.
--
-- Consequence worth stating plainly: `n_bonded_sev5` is NOT an input. A run row supplied with a
-- non-zero value and no corresponding checks cannot exist. That is the S10 promise —
-- *a fatality in your fonds is always recalled* — expressed as arithmetic the database keeps.
--
-- ACYCLICITY. The trigger graph stays depth 1: this fires on `mainline.blocking_check` and
-- writes `mainline_meas.recall_run`, whose only trigger is BEFORE INSERT (0136). An UPDATE
-- therefore cannot re-enter, and no path returns to `blocking_check`.
--
-- SCOPE. `recall_run` is permit-scoped by DM-15 (CR-scoped checks come from channel A's
-- deterministic `fn_weaken_materialise`, which needs no retrieval), so a change-request check
-- returns early. A check with no precursor event — `weaken_over_blood`, whose precursor is a
-- clause ancestry rather than a single event — likewise returns early.
--
-- IDEMPOTENCE rests on `blocking_check.dedupe_key` (§5.5, owned by `dm-gate`): the same
-- precursor cannot land twice for one subject, so the counter cannot double-count. That
-- dependency is named here rather than defended twice.
--
-- NO RECALL RUN, NO ARITHMETIC. If a bonded severity-5 check lands on a permit that has no
-- `recall_run` row, the UPDATE matches nothing and both counters stay at zero. That is the
-- correct behaviour and not a hole: `recall_run` is the accounting for a RETRIEVAL, and a
-- deterministic channel-A check (`fn_weaken_materialise`) materialises without one. MI16 is a
-- statement about what a run may CLAIM, and a run that does not exist claims nothing. The
-- obligation itself is already in `blocking_check` and already holds the gate shut.
--
-- Style (§5.11): PL/pgSQL, row-level, no FOR..IN, no FOREACH, no EXECUTE, no PERFORM, no CASE;
-- IF/ELSIF plus exactly one aggregate SELECT..INTO.
--
-- PLATFORM: CockroachDB requires `OLD`/`NEW` to be parenthesised when a COLUMN is read —
-- `(NEW).permit_id`, not `NEW.permit_id` — a documented known limitation whose own v26.2
-- examples read `(NEW).wage` and assign `NEW.wage := …`. ARCHITECTURE §5.11 is written in the
-- unparenthesised PostgreSQL style; every trigger in the deployment needs this correction.

CREATE FUNCTION mainline.fn_bonded_sev5() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  n_bonded INT8;
BEGIN
  IF (NEW).permit_id IS NULL OR (NEW).precursor_event_id IS NULL THEN
    RETURN NEW;
  END IF;

  -- Authoritative: is this precursor a severity-5 event bonded to an activity node at all?
  -- Derived from event_bond ⋈ event. Never from the inserter, and never from
  -- blocking_check.severity, which is itself a projection of a different table.
  SELECT count(*) INTO n_bonded
    FROM mainline.event_bond eb
    JOIN mainline.event ev ON ev.event_id = eb.event_id
   WHERE eb.event_id = (NEW).precursor_event_id
     AND ev.severity_gate = 5;

  IF n_bonded = 0 THEN
    RETURN NEW;
  END IF;

  -- RD-1: the pair moves together, in one statement, so the CHECK holds at every statement
  -- boundary. See 0081 for why no other ordering is expressible.
  UPDATE mainline_meas.recall_run
     SET n_bonded_sev5          = n_bonded_sev5 + 1,
         n_bonded_sev5_blocking = n_bonded_sev5_blocking + 1
   WHERE run_id = (SELECT r.run_id
                     FROM mainline_meas.recall_run r
                    WHERE r.permit_id = (NEW).permit_id
                    ORDER BY r.started_at DESC
                    LIMIT 1);

  RETURN NEW;
END $$;
