-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI17, MI25
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: Severity is not a label on a recall candidate, it is the threshold the candidate is judged against, so an inserter able to write it could move a fatality's evidence bar and produce a silence-ledger row that reads as a careful calibrated judgement; this function makes the severity in the row be the severity in `mainline.event`, for every writer.
--
-- migration:  0110_fn_candidate_project
-- band:       0110-0114z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). `0110` is the
--             free head of recall's function band; see WHY THIS FILE EXISTS below.
-- domain:     recall
-- statements: 1
-- source:     ARCHITECTURE.md §5.7 ("PROJECTED from event.severity_gate (S10)") · §5.11
-- requires:   0033 mainline.event
-- provides:   mainline.fn_candidate_project() — welded to mainline_meas.recall_candidate by 0139
-- sqlstate:   P0001
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- ── WHY THIS FILE EXISTS (migration reconciliation, 2026-08-08) ───────────────────────────────
-- This function was written inside `0139_trg_candidate_project.sql`, as the first of that file's
-- two statements. Its own header gave the reason: "the recall band reserves three function
-- numbers (0112-0114) and four trigger numbers (0136-0139), so this projector has no function
-- file of its own; rather than take a number this domain does not own, the function ships welded
-- to its trigger."
--
-- **That premise is now false and the shape it forced was wrong twice over.**
--
-- It is false because `migrations.allocation.toml` grants recall `0110`-`0114z`, not `0112`-`0114`
-- (MR-7 adopts kernel D8's extension of §18's ranges and revokes datamodel's remap). `0110` and
-- `0111` were free the whole time. The worker did not have to borrow; it had to look at a
-- declaration that did not yet exist, which is the incident this reconciliation is about.
--
-- It was wrong first because a `CREATE FUNCTION` in a file numbered `0139` inverts §18's
-- stratification: functions are created in `0100`-`0119`, triggers in `0120`-`0139`. The
-- inversion is invisible until the moment a trigger in `0130`-`0138` wants to call
-- `fn_candidate_project` — at which point the function does not exist yet and the failure is a
-- missing-object error in someone else's migration, with nothing in the diagnosis pointing here.
--
-- It was wrong second because the file carried two top-level statements. The runner does not
-- wrap a file body in a transaction, because CockroachDB DDL is not transactional across
-- statements: a two-statement file that fails on its second leaves the schema half-applied with
-- the version unrecorded, and the `dirty` marker names a FILE rather than a STATEMENT. One
-- statement per file is what makes `dirty` answerable in seconds instead of undiagnosable.
--
-- The original header offered a compensating benefit — "these two statements can never drift
-- apart across environments". They still cannot: `0110` and `0139` are two versions in one
-- forward-only chain applied by one `trappoint migrate up`, and the only state in which the
-- function exists without its trigger is a run that stopped between them, which is precisely the
-- state the one-statement rule exists to make legible.
--
-- ── WHAT AN INSERTER COULD DO WITH A WRITABLE `severity` ─────────────────────────────────────
-- Severity-Graded Admission lowers the evidence bar as severity rises — τ(5)=0.35, τ(4)=0.45,
-- τ(3)=0.60, τ(2)=0.75, τ(1)=0.85 — so severity is not a label on the candidate, it is the
-- threshold the candidate is judged against. An agent able to write `severity=1` on a fatality
-- would move that fatality's bar to 0.85, watch it fall below, and produce a silence-ledger row
-- that reads as a careful, calibrated, well-documented judgement. Every artefact downstream
-- would corroborate it. The projection is what makes that story unwritable: the severity in the
-- row is the severity in `mainline.event`, for every writer, and a candidate naming an event
-- that does not exist cannot be typed at all.
--
-- Note the asymmetry with `blocking_check.severity` (§5.11 #1), which projects from the blame
-- CLOSURE. A recall candidate is a claim about ONE event, so its authoritative source is that
-- event's own gate severity; a blocking check is a claim about a clause's whole ancestry. Using
-- the closure here would be wrong, and using the event there would be S1 all over again.
--
-- Style (§5.11): PL/pgSQL, row-level, no FOR..IN, no FOREACH, no EXECUTE, no PERFORM, no CASE;
-- IF plus exactly one SELECT..INTO.
--
-- PLATFORM: CockroachDB requires `OLD`/`NEW` to be parenthesised when a COLUMN is read —
-- `(NEW).event_id`, not `NEW.event_id` — a documented known limitation whose own v26.2 examples
-- read `(NEW).wage` and assign `NEW.wage := …`. The assignment target below is deliberately
-- bare, matching that example. ARCHITECTURE §5.11 is written in the unparenthesised PostgreSQL
-- style; every trigger in the deployment needs this correction.

CREATE FUNCTION mainline.fn_candidate_project() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  ev_sev INT2;
BEGIN
  SELECT e.severity_gate INTO ev_sev
    FROM mainline.event e
   WHERE e.event_id = (NEW).event_id;

  IF ev_sev IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no such event — a recall candidate cannot be typed';
  END IF;

  NEW.severity := ev_sev;
  RETURN NEW;
END $$;
