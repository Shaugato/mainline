-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI14, MI16
-- I: I11, I13
-- COUNSEL-GATED: no
-- RATIONALE: MI14 is a plain-column CHECK over two columns of this row and nothing else, because the sentence it enforces — a language model's rating may never be the reason a permit was refused — has to hold for every writer including a DBA, and any enforcement that lives above the database is enforcement the adversary it exists to constrain can simply not call.
--
-- migration:  0033_event
-- band:       0032-0036 · dm-event-severity (activity taxonomy, events, and the severity record)
-- statements: 1
-- source:     ARCHITECTURE.md §5.4 (verbatim shape; constraints named per DM-10, index inline per DM-6)
-- requires:   0002 CREATE SCHEMA mainline
-- consumed:   0034 event_edge · 0035 control_failure · 0036 event_severity_revision ·
--             0037 blame_edge · 0040 event_cue · 0043-0046 the lexical channel and the bond set
-- sqlstate:   23514 on model_cannot_arm and the range/vocabulary CHECKs;
--             23505 on one_event_per_external_ref
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `model_cannot_arm` IS THE LINE. An LLM's severity rating may never arm a blocking gate.
--     CHECK (severity_gate < 4 OR severity_basis <> 'model_rated')
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- The constraint is worth more than the sentence, because the sentence is a promise and the
-- constraint is a fact about the cluster. The first question in cross-examination after a permit
-- was refused is "who decided?", and there is exactly one answer this system is prepared to give
-- under oath: a coded field, a regulator's classification, or a named human. `model_rated` is
-- allowed to exist, allowed to be shown, allowed to be argued with, and allowed to be promoted
-- by a person who puts their name on it — and it is not allowed to reach 4. Rated 5 by a model,
-- the event still sits in the record at `severity_gate = 3` with `severity_potential = 5`, which
-- is a visible, quotable disagreement between what the machine thought and what the gate did.
-- That row is a better exhibit than a green test suite.
--
-- THREE SEVERITIES, NOT ONE, AND THEY ARE THREE DIFFERENT SENTENCES:
--
--   severity_actual     what happened. A coded consequence, usually from the buyer's own system.
--   severity_potential  what could reasonably have happened. This is where hindsight and
--                       model inference live, and it is deliberately NOT the gate.
--   severity_gate       what this system will act on. In the reference corpus it is
--                       max(severity_actual, potential_admitted) where `potential_admitted` is
--                       the portion of the potential a human or a coded field stands behind.
--
-- No CHECK ties `severity_gate` to the other two, and that absence is a decision, not an
-- oversight. The obvious constraint — `severity_gate >= severity_potential` — would contradict
-- `model_cannot_arm` on exactly the row that matters most: a model rating a near-miss at
-- potential 5 must leave the gate at 3. Two CHECKs that jointly make a legitimate row
-- unrepresentable is how a schema quietly stops recording the cases it was built for. The
-- relation between the three is `fn_event_severity_guard`'s to enforce (band 0130-0199) once the
-- admitted-potential column it needs exists; until then the corpus builder re-derives it and
-- refuses to emit a skeleton that violates it.
--
-- BITEMPORAL, BOTH, ALWAYS. `occurred_at` is when the world changed; `ingested_at` is when this
-- record learned about it. Twenty-two-year-old blame is normal here — an incident from 2004
-- ingested in 2026 is the ordinary case, not the edge case — so the pair can be arbitrarily far
-- apart in one direction and cannot be inverted in the other. `ingested_before_occurrence`
-- refuses an event recorded before it happened; a system that accepts one has no basis to claim
-- any of its timestamps mean anything. (The CHECK compares two columns of the row being written.
-- `now()` appears only as a DEFAULT, never inside a CHECK — DM-4.)
--
-- `severity_span` and `source_sha256` ARE THE QUOTE DISCIPLINE. The gate's refusal will be read
-- aloud, so the severity has to be traceable to a byte range in a document whose bytes are
-- pinned in S3 under Object Lock and whose digest is in this row. A severity with no span is a
-- number somebody typed.
--
-- `site_id` CARRIES NO FOREIGN KEY, and that is ARCHITECTURE §5's shape across all forty tables
-- that hold it — recorded here rather than silently followed. It becomes load-bearing when the
-- projection triggers in band 0130-0199 read `mainline.site` (DM-3) and RAISE P0001 on a missing
-- row. Until then a site_id here is a client-supplied value, and no gate reads it.

CREATE TABLE mainline.event (
  event_id           UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_id            UUID        NOT NULL,   -- authoritative source: mainline.site (DM-3)
  external_ref       STRING      NULL,       -- the buyer's own incident number
  occurred_at        TIMESTAMPTZ NOT NULL,   -- bitemporal: when the world changed
  ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),   -- bitemporal: when we learned
  kind               STRING      NOT NULL,
  title              STRING      NOT NULL,
  narrative          STRING      NOT NULL,
  source_doc_id      UUID        NULL,
  source_object_key  STRING      NOT NULL,   -- S3 Object Lock version id of the raw bytes
  source_sha256      BYTES       NOT NULL,
  severity_actual    INT2        NOT NULL,   -- what happened
  severity_potential INT2        NOT NULL,   -- what could have happened. NOT the gate.
  severity_gate      INT2        NOT NULL,   -- what this system acts on
  severity_basis     STRING      NOT NULL,   -- who says so. `model_rated` may not reach 4.
  severity_span      INT8[]      NULL,       -- byte range in the source the rating was read from
  consequence_proxy  JSONB       NULL,       -- energy / exposure-minutes / loss
  cluster_id         UUID        NULL,
  canon_version      INT2        NOT NULL,
  CONSTRAINT event_pk PRIMARY KEY (event_id),
  -- Named to avoid the substring `_ref_`: dm-foundation's DM-10 probe treats it as CockroachDB's
  -- generated FK shape (`fk_<col>_ref_<table>`), and `event_external_ref_unique` would trip it.
  CONSTRAINT one_event_per_external_ref UNIQUE (site_id, external_ref),
  CONSTRAINT kind_closed CHECK (kind IN
    ('incident', 'near_miss', 'regulator_notice', 'oem_alert', 'audit_finding', 'capa')),
  CONSTRAINT severity_basis_closed CHECK (severity_basis IN
    ('coded_field', 'regulator_class', 'human_rated', 'model_rated')),
  -- MI14. An LLM's rating alone may never arm a blocking gate.
  CONSTRAINT model_cannot_arm CHECK (severity_gate < 4 OR severity_basis <> 'model_rated'),
  CONSTRAINT severity_actual_in_range CHECK (severity_actual BETWEEN 0 AND 5),
  CONSTRAINT severity_potential_in_range CHECK (severity_potential BETWEEN 0 AND 5),
  CONSTRAINT severity_gate_in_range CHECK (severity_gate BETWEEN 0 AND 5),
  CONSTRAINT severity_span_is_a_pair CHECK
    (severity_span IS NULL OR array_length(severity_span, 1) = 2),
  CONSTRAINT ingested_before_occurrence CHECK (ingested_at >= occurred_at),
  CONSTRAINT title_stated CHECK (title <> ''),
  CONSTRAINT narrative_stated CHECK (narrative <> ''),
  CONSTRAINT source_object_key_stated CHECK (source_object_key <> ''),
  CONSTRAINT source_sha256_is_a_digest CHECK (length(source_sha256) = 32),
  CONSTRAINT canon_version_positive CHECK (canon_version >= 1),
  INDEX by_sev (site_id, severity_gate, occurred_at DESC)
);
