-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI13, MI16
-- I: I11, I13
-- COUNSEL-GATED: no
-- RATIONALE: `control_class` is the JOIN KEY that turns "did this change address that failure?" from a prose judgement into a set operation against a clause's Control Assertion Tuple, and a schema that let each ingest mint its own class string would produce a corpus in which every intersection is empty, every derived_documentary blame edge is unreachable, and the basis-graded force of MI13 is never exercised at all.
--
-- migration:  0035_control_failure
-- band:       0032-0036 · dm-event-severity (activity taxonomy, events, and the severity record)
-- statements: 1
-- source:     ARCHITECTURE.md §5.4 (verbatim shape; constraints named per DM-10, index inline per DM-6);
--             icam_tier vocabulary from verticals/mainline/packages/mainline-corpus/.../control_classes.yaml
-- requires:   0033 mainline.event
-- consumed:   the `derived_documentary` blame-edge rule · the `mechanism` recurrence cue synthesis
-- sqlstate:   23514 on the four closed vocabularies, evidence_span_is_a_pair and
--             quote_sha256_is_a_digest; 23503 on fk_event
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ICAM AND BOWTIE, NORMALISED TO ONE SHAPE. Every investigation methodology a mine site actually
-- uses produces the same three facts about a barrier — which one, what role it played, how it
-- failed — under four different sets of words. This table is that intersection, and normalising
-- to it is what makes an OEM alert from a vendor and an ICAM report from a regulator comparable
-- at all.
--
-- WHY `control_class` IS A CLOSED SHARED VOCABULARY AND `derived_documentary` DEPENDS ON IT.
-- A clause's CAT (Control Assertion Tuple) names a control class; this row names a control class;
-- the intersection is a set operation a database can do and a `derived_documentary` blame edge is
-- exactly the assertion that the intersection is non-empty and re-derivable. That is the basis
-- MI13 permits to block. If the vocabulary drifts — one ingest writing `LOTO`, another
-- `POSITIVE_ISOLATION_APPLICATION` — the intersection is empty, no derived edge is ever
-- computed, and the only edges left are `inferred_semantic` ones, which MI13 forbids from
-- blocking. The gate would then be silent for a reason no test asserts and no error reports.
-- The vocabulary lives in the corpus gazetteer (`control_classes.yaml`) rather than in a CHECK
-- here because the buyer's control set is customer data, not schema; the CI cross-check in
-- tests/integration/schema/test_mi_event_severity.py asserts the two agree.
--
-- `icam_tier` IS CLOSED, and the four values are the standard ICAM tiers spelled exactly as the
-- reference corpus already writes them. A NULL is permitted — many source documents are not ICAM
-- reports and inventing a tier for them would be fabrication — but a non-NULL value that is not
-- one of the four is a typo that would silently disappear from every tier rollup.
--
-- `evidence_span` + `quote_sha256` ARE THE QUOTE DISCIPLINE, AND THEY ARE NOT OPTIONAL HERE.
-- Nullable evidence is how a control failure becomes an allegation. The span is a byte range in
-- the source document and the digest is over the exact quoted bytes, so the console can show the
-- sentence the finding came from and a verifier can prove the sentence was not edited afterwards.
-- `evidence_span` is declared `INT8[2]`, matching §5.4 and migration 0040 — but an array
-- dimension is NOT ENFORCED by PostgreSQL or CockroachDB, it is documentation that looks like a
-- constraint. `evidence_span_is_a_pair` is the enforcement, and it is why the declaration is
-- allowed to stay decorative.
--
-- `array_length` and `length(BYTES)` are immutable builtins (DM-4 permits only documented ones);
-- `length(commit_id) = 32` is already how migration 0024 states the same idea, so this file
-- follows the spine rather than inventing a second spelling. UNVERIFIED against a live v26.2 on
-- the machine this file was written on: if either is rejected inside a CHECK, delete that one
-- CONSTRAINT line and the assertion moves to the schema test — nothing else in the band depends
-- on it.

CREATE TABLE mainline.control_failure (
  failure_id    UUID    NOT NULL DEFAULT gen_random_uuid(),
  event_id      UUID    NOT NULL,
  control_class STRING  NOT NULL,   -- THE JOIN KEY to a clause's CAT control class
  barrier_role  STRING  NOT NULL,
  failure_mode  STRING  NOT NULL,
  icam_tier     STRING  NULL,
  hazard_energy STRING  NOT NULL,
  evidence_span INT8[2] NOT NULL,   -- dimension is decoration; the CHECK is the enforcement
  quote_sha256  BYTES   NOT NULL,
  CONSTRAINT control_failure_pk PRIMARY KEY (failure_id),
  CONSTRAINT fk_event FOREIGN KEY (event_id) REFERENCES mainline.event (event_id),
  CONSTRAINT barrier_role_closed CHECK (barrier_role IN ('preventive', 'recovery')),
  CONSTRAINT failure_mode_closed CHECK (failure_mode IN
    ('absent', 'ineffective', 'bypassed', 'degraded', 'not_verified')),
  CONSTRAINT hazard_energy_closed CHECK (hazard_energy IN
    ('gravity', 'pressure', 'electrical', 'thermal', 'chemical', 'kinetic',
     'biological', 'radiation')),
  CONSTRAINT icam_tier_closed CHECK (icam_tier IS NULL OR icam_tier IN
    ('absent_or_failed_defence', 'individual_or_team_action',
     'task_or_environmental_condition', 'organisational_factor')),
  CONSTRAINT control_class_stated CHECK (control_class <> ''),
  CONSTRAINT evidence_span_is_a_pair CHECK (array_length(evidence_span, 1) = 2),
  CONSTRAINT quote_sha256_is_a_digest CHECK (length(quote_sha256) = 32),
  INDEX by_class (control_class, event_id),
  INDEX by_event (event_id, control_class)
);
