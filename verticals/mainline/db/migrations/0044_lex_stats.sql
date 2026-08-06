-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0044_lex_stats
-- domain:     recall
-- statements: 1
-- invariants: MI17
-- source:     ARCHITECTURE.md §5.4
-- requires:   0001 CREATE SCHEMA mainline
-- sqlstate:   —
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- Document frequency per term, per site. This is the table that makes IDF exist at all, and IDF
-- is the reason channel D is worth building: without it a permit mentioning "the" and "K-401"
-- scores both the same way and the rare identifier — the only token that carries the hazard —
-- is drowned. `df` is maintained by the lexical writer, never by a gate.

CREATE TABLE mainline.lex_stats (
  site_id UUID   NOT NULL,
  term    STRING NOT NULL,
  df      INT8   NOT NULL,
  CONSTRAINT lex_stats_pk PRIMARY KEY (site_id, term),
  CONSTRAINT df_positive CHECK (df >= 0)
);
