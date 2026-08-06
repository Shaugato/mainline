-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0043_lex_posting
-- domain:     recall
-- statements: 1
-- invariants: MI17 (channel D's hits are counted in the conserved candidate partition)
-- source:     ARCHITECTURE.md §5.4
-- requires:   0001 CREATE SCHEMA mainline
-- sqlstate:   —
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- CockroachDB has no BM25, and `ts_rank` has neither IDF nor length normalisation (a PostgreSQL
-- FTS semantics fact, not a CockroachDB gap). For a channel whose entire job is `K-401`, `H2S`,
-- `%LEL` and OEM part numbers, a scorer without IDF is disqualifying: the rare identifier is
-- the signal. So the posting list, the document frequencies (0044) and the document lengths
-- (0045) are explicit tables and BM25 (k1 = 1.2, b = 0.75) is explicit SQL.
--
-- `weight` is the in-document term weight (term frequency after the field weighting the
-- tokeniser applies), not a score. Scores are computed at query time from all three tables.

CREATE TABLE mainline.lex_posting (
  site_id  UUID   NOT NULL,
  term     STRING NOT NULL,
  event_id UUID   NOT NULL,
  weight   FLOAT8 NOT NULL,
  CONSTRAINT lex_posting_pk PRIMARY KEY (site_id, term, event_id)
);
