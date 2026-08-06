-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0045_lex_doclen
-- domain:     recall
-- statements: 1
-- invariants: MI17
-- source:     ARCHITECTURE.md §5.4
-- requires:   0001 CREATE SCHEMA mainline
-- sqlstate:   —
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
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
