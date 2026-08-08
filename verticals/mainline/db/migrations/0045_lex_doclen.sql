-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI17
-- I: I13
-- COUNSEL-GATED: no
-- RATIONALE: MSHA Part 50 narratives are VARCHAR2(384) while a CSB investigation report is tens of pages; without |d|/avgdl the long document wins every comparison for reasons that have nothing to do with recurrence.
--
-- migration:  0045_lex_doclen
-- band:       0040-0046z · recall/recall-ddl-triggers · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- domain:     recall
-- statements: 1
-- source:     ARCHITECTURE.md §5.4
-- requires:   0001a CREATE SCHEMA mainline (RENDERED; template 0001_schemas.sql.j2)
-- sqlstate:   —
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- Length normalisation, the other half of what `ts_rank` does not have. MSHA Part 50 narratives
-- are VARCHAR2(384) while a CSB investigation report is tens of pages; without |d|/avgdl the
-- long document wins every comparison for reasons that have nothing to do with recurrence.

CREATE TABLE mainline.lex_doclen (
  event_id UUID NOT NULL,
  len      INT8 NOT NULL,
  CONSTRAINT lex_doclen_pk PRIMARY KEY (event_id),
  CONSTRAINT len_positive CHECK (len >= 0)
);
