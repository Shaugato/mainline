-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0139_trg_candidate_project
-- domain:     recall
-- statements: 2 — CREATE FUNCTION then CREATE TRIGGER. The recall band reserves three function
--             numbers (0112–0114) and four trigger numbers (0136–0139), so this projector has
--             no function file of its own; rather than take a number this domain does not own,
--             the function ships welded to its trigger. The side effect is desirable: these two
--             statements can never drift apart across environments.
-- invariants: MI25 (the projection principle), MI17 (this table is the conserved partition)
-- source:     ARCHITECTURE.md §5.7 ("PROJECTED from event.severity_gate (S10)") · §5.11
-- requires:   0082 mainline_meas.recall_candidate · 0033 mainline.event
-- sqlstate:   P0001
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- WHAT AN INSERTER COULD DO WITH A WRITABLE `severity`. Severity-Graded Admission lowers the
-- evidence bar as severity rises — τ(5)=0.35, τ(4)=0.45, τ(3)=0.60, τ(2)=0.75, τ(1)=0.85 — so
-- severity is not a label on the candidate, it is the threshold the candidate is judged against.
-- An agent able to write `severity=1` on a fatality would move that fatality's bar to 0.85,
-- watch it fall below, and produce a silence-ledger row that reads as a careful, calibrated,
-- well-documented judgement. Every artefact downstream would corroborate it. The projection is
-- what makes that story unwritable: the severity in the row is the severity in `mainline.event`,
-- for every writer, and a candidate naming an event that does not exist cannot be typed at all.
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

CREATE TRIGGER candidate_project BEFORE INSERT ON mainline_meas.recall_candidate
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_candidate_project();
