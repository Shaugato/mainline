-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0040_event_cue
-- domain:     recall
-- statements: 1
-- invariants: MI16, MI17
-- source:     ARCHITECTURE.md §5.4 (verbatim, index declared inline per DM-6)
-- requires:   0001 CREATE SCHEMA mainline · 0033 mainline.event
-- sqlstate:   23505 on the (event_id, scope_id, facet, prompt_version) uniqueness
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- The ENTITY of the recall memory. No vector column lives here (S21): the vectors are in two
-- sidecars, 0041 and 0042, and BOTH of them take their prefix columns FROM THIS ROW by trigger
-- (0114/0138). That is the whole point of splitting the entity out — there is exactly one
-- authoritative statement of "which archival tree does this cue belong to", and it is this row.
--
-- ONE ROW PER ARCHIVAL LEVEL (Level-Materialised Bonds). A single event contributes a cue row at
-- level 1 (fonds), 2 (series) and 3 (file) for each facet, which is what grades the C-SPANN tree
-- sizes and makes "one constrained arm per ancestor" both correct and necessary. With one
-- inherited prefix, the ancestor walk collapses to a single arm and the design is a slogan.
--
-- `is_derived` is not decoration: a synthesised cue may NEVER be quoted to a human without its
-- event, because a cue is a model's paraphrase of an incident and displaying it alone would be
-- an unattributed machine statement about a real workplace death.

CREATE TABLE mainline.event_cue (
  cue_id       UUID   NOT NULL DEFAULT gen_random_uuid(),
  event_id     UUID   NOT NULL REFERENCES mainline.event (event_id),
  site_id      UUID   NOT NULL,
  scope_id     UUID   NOT NULL,                 -- ONE ROW PER ARCHIVAL LEVEL (LMB)
  scope_level  INT2   NOT NULL CHECK (scope_level BETWEEN 1 AND 3),
  facet        STRING NOT NULL CHECK (facet IN
    ('mechanism','precondition','control_failure','recurrence_test','narrative')),
  taxonomy_ver INT4   NOT NULL,
  cue_text     STRING NOT NULL,
  source_span  INT8[2] NULL,
  is_derived   BOOL   NOT NULL DEFAULT true,    -- a cue may NEVER be quoted without its event
  gen_model    STRING NOT NULL,
  prompt_version STRING NOT NULL,
  tsv          TSVECTOR AS (to_tsvector('english', cue_text)) STORED,
  CONSTRAINT event_cue_pk PRIMARY KEY (cue_id),
  CONSTRAINT event_cue_one_per_scope_facet_prompt
    UNIQUE (event_id, scope_id, facet, prompt_version),
  INVERTED INDEX cue_tsv (tsv)
);
