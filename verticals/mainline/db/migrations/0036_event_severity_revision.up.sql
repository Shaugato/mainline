-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI14, MI15
-- I: I11, I05
-- COUNSEL-GATED: no
-- RATIONALE: The cheapest attack on MAINLINE is not rewording a clause, it is re-rating the event — a single UPDATE dropping `severity_gate` from 5 to 3 would retract blame obligations across every descendant clause, fleet-wide, silently and with no refusal anywhere — so the re-rating is not an UPDATE at all: it is a signed, append-only row that costs a different rater and a hundred and twenty characters of reasons.
--
-- migration:  0036_event_severity_revision
-- band:       0032-0036 · dm-event-severity (activity taxonomy, events, and the severity record)
-- statements: 1
-- source:     ARCHITECTURE.md §5.4 (verbatim shape; constraints named per DM-10, index inline per DM-6)
-- requires:   0024 mainline.commit_obj · 0033 mainline.event
-- consumed:   fn_severity_revision_materialise (band 0130-0199) · mainline_meas.silence_ledger
-- sqlstate:   23514 on downgrade_needs_new_rater / substantive / the range and shape CHECKs;
--             23503 on fk_event / fk_commit
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- UPGRADES ARE FREE. DOWNGRADES COST A SIGNATURE, A SECOND PERSON, AND A PARAGRAPH.
--     CONSTRAINT downgrade_needs_new_rater
--       CHECK (to_gate >= from_gate OR rater_sub <> prior_rater_sub)
--     CONSTRAINT substantive CHECK (length(rationale) >= 120)
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHY THIS TABLE EXISTS AT ALL. Everything ancestry-conditioned in MAINLINE reads one scalar —
-- the blame closure's `max_severity` and the `virulence` banded from it. That scalar's ultimate
-- source is `event.severity_gate`. Every gate, every clearance-lattice 23503, every drift
-- finding and every weaken-over-blood refusal is downstream of it. So the attack surface is not
-- the gate: it is this number. An operator who cannot get a permit through has two options —
-- disposition the check on the record with their name on it, or quietly re-rate the incident
-- from a 5 to a 3 and watch every refusal in the fleet evaporate at once, with no signature, no
-- ledger entry and no exception.
--
-- The asymmetry is the whole design. Raising a severity adds obligations, and a system that
-- makes it expensive to admit something was worse than recorded is a system that teaches people
-- not to. So an upgrade needs nothing beyond the row itself. Lowering a severity SUBTRACTS
-- obligations that other people are relying on, so it costs:
--
--   1. a DIFFERENT RATER      `downgrade_needs_new_rater` — the person who cannot get their
--                             permit through is precisely the person who may not be the one who
--                             decides the incident was less serious than recorded. Two named
--                             people, or it does not happen.
--   2. A HUNDRED AND TWENTY   `substantive` — long enough that "reviewed" and "n/a" and "per
--      CHARACTERS OF REASONS  discussion" do not fit. This is a crude instrument and it is
--                             chosen deliberately over a subtler one: a length CHECK is
--                             row-local, immutable, needs no service, and cannot be talked out
--                             of at 3 a.m. It does not make the rationale good. It makes the
--                             absence of a rationale a refusal instead of a blank field.
--   3. A SIGNATURE            over the commit envelope, verifiable by a third party without us.
--   4. A COMMIT               `commit_id` — the revision is a commit in the repository, so it
--                             has parents, a ref, and a place in the DAG a stranger can walk.
--
-- WHAT STILL HAS TO BE BUILT ON TOP, STATED HONESTLY. §5.4 requires that a downgrade from
-- `severity_gate >= 4` MATERIALISE ITS OWN BLOCKING CHECK listing every check it would
-- extinguish, and write a silence-ledger entry per extinguished check. That is
-- `fn_severity_revision_materialise`, band 0130-0199, owned by dm-functions-triggers. It is NOT
-- in this file and this file does not pretend otherwise: today a row here records the intent to
-- re-rate and satisfies the four costs above, and the propagation to `event.severity_gate` and
-- to the closure does not happen at all. The table is inert until S8, exactly like every other
-- table in strata S1-S7.
--
-- TWO COLUMNS HERE ARE PROJECTIONS AND ARE NOT YET ENFORCED AS ONE (P2, MI15). This is the most
-- important unfinished sentence in the band, so it is written out rather than implied:
--
--   from_gate        MUST be written by trigger from mainline.event.severity_gate — the CURRENT
--                    value, read inside the same transaction — and the trigger MUST RAISE P0001
--                    when the event row is absent. A client-supplied `from_gate` defeats
--                    `downgrade_needs_new_rater` completely and trivially: declare from_gate = 0,
--                    to_gate = 3, and the CHECK reads it as an UPGRADE. The constraint is only
--                    as strong as the provenance of the column it reads, which is the entire
--                    content of P2 and the exact shape of adversarial finding S1.
--   prior_rater_sub  MUST be written by trigger from the latest prior revision of the same event
--                    (or from the event's own severity provenance when none exists). A
--                    client-supplied value defeats the two-person rule by naming somebody else.
--
-- Both must appear in TRIGGER-MAP.yaml, owned by dm-functions-triggers:
--     from_gate       ⇄ fn_severity_revision_project ⇄ mainline.event                   ⇄ P0001
--     prior_rater_sub ⇄ fn_severity_revision_project ⇄ mainline.event_severity_revision ⇄ P0001
-- and tests/integration/schema/test_mi_event_severity.py carries the PL-2 RED case asserting
-- that no such function exists yet. It fails today, on purpose, for that reason.
--
-- `a_revision_changes_something` is stricter than §5.4 and costs nothing: a revision from 3 to 3
-- is not a re-rating, it is a note, and admitting it here would let an attacker accumulate
-- `prior_rater_sub` history — each no-op row silently becoming the "prior rater" of the next —
-- until the two-person rule is satisfied by a chain of one person's own no-ops. That is a real
-- defeat of `downgrade_needs_new_rater`, and one CHECK removes it.
--
-- `sig` is a WebAuthn assertion signature (§11.4), so its length is format-dependent — DER
-- ECDSA P-256 is variable, Ed25519 is 64 — and a fixed-length CHECK here would be wrong the
-- first time an authenticator model changed. `sig_present` refuses the actual attack, which is
-- an empty BYTES literal written to get past NOT NULL. Verification is `trappoint-verify`
-- check 12, and it is a different layer on purpose.

CREATE TABLE mainline.event_severity_revision (
  revision_id     UUID        NOT NULL DEFAULT gen_random_uuid(),
  event_id        UUID        NOT NULL,
  commit_id       BYTES       NOT NULL,   -- sha256 over the canonical (JCS) commit envelope
  from_gate       INT2        NOT NULL,   -- PROJECTED (pending): mainline.event.severity_gate
  to_gate         INT2        NOT NULL,
  rationale       STRING      NOT NULL,
  rater_sub       STRING      NOT NULL,
  prior_rater_sub STRING      NOT NULL,   -- PROJECTED (pending): the latest prior revision
  sig             BYTES       NOT NULL,
  at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT event_severity_revision_pk PRIMARY KEY (revision_id),
  CONSTRAINT fk_event FOREIGN KEY (event_id) REFERENCES mainline.event (event_id),
  CONSTRAINT fk_commit FOREIGN KEY (commit_id) REFERENCES mainline.commit_obj (commit_id),
  -- Upgrades are free; downgrades cost a different person.
  CONSTRAINT downgrade_needs_new_rater
    CHECK (to_gate >= from_gate OR rater_sub <> prior_rater_sub),
  -- Long enough that "reviewed", "n/a" and "per discussion" do not fit.
  CONSTRAINT substantive CHECK (length(rationale) >= 120),
  CONSTRAINT a_revision_changes_something CHECK (to_gate <> from_gate),
  CONSTRAINT from_gate_in_range CHECK (from_gate BETWEEN 0 AND 5),
  CONSTRAINT to_gate_in_range CHECK (to_gate BETWEEN 0 AND 5),
  CONSTRAINT rater_sub_stated CHECK (rater_sub <> ''),
  CONSTRAINT prior_rater_sub_stated CHECK (prior_rater_sub <> ''),
  CONSTRAINT commit_id_is_sha256 CHECK (length(commit_id) = 32),
  CONSTRAINT sig_present CHECK (length(sig) > 0),
  INDEX by_event (event_id, at DESC),
  INDEX by_commit (commit_id)
);
