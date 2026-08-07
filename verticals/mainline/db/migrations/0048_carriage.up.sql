-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI19, MI01
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: This table is the AUTHORITATIVE SOURCE behind mainline.doc.open_token_count, and therefore behind MI19 — a carriage row with no closing commit is exactly what "this document still carries a live control" means, and the projection trigger that counts these rows must RAISE rather than default to zero.
--
-- migration:  0048_carriage
-- band:       0024-0031, 0047-0049 · dm-spine
-- statements: 1
-- source:     ARCHITECTURE.md §5.3 (verbatim shape; constraints named per DM-10, partial index
--             inline per DM-6) · §16 MI19 · docs/adr/0002-g1-platform-ground-truth.md GT-14
-- requires:   0024 mainline.commit_obj · 0027 mainline.doc · 0047 mainline.control_series
-- projects:   nothing. AUTHORITATIVE for mainline.doc.open_token_count (0027) — the P2 source
--             `fn_doc_token_count` (band 0130-0199) must read, and must RAISE P0001 when it
--             cannot.
-- sqlstate:   23503 on fk_series / fk_doc / fk_opened_commit / fk_closed_commit;
--             23505 on carriage_pk and on carriage_one_open (the partial unique index)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE TIME-BOUNDED LINK. A control series (0047) persists; a document (0027) carries it for a
-- while. One row here says: "from commit `opened_commit` until commit `closed_commit`, series S
-- lived in document D." `closed_commit IS NULL` means it still does — and that NULL is the single
-- fact MI19 is computed from.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- HOW MI19 IS ACTUALLY COMPUTED, END TO END. Four steps, and the interesting one is the third:
--
--   1. Someone opens carriage: a row here with `closed_commit IS NULL`.
--   2. `fn_doc_token_count` (band 0130-0199) fires and writes
--      `mainline.doc.open_token_count = <count of open carriage rows for that doc_id>`.
--      It reads THIS table. It does not read the inserter. If it cannot resolve the doc, it
--      RAISEs P0001 — it never writes 0 as a fallback.
--   3. Someone tries to supersede the document. `no_orphan_controls` on mainline.doc —
--      `CHECK (state <> 'superseded' OR open_token_count = 0)` — refuses with 23514.
--   4. To supersede it, they must first close each carriage, which means either another document
--      opens carriage of that series, or the series is retired with a named author (0047). Either
--      way, the control's disappearance is an ACT that somebody performed, not a side effect of
--      tidying a document.
--
-- Step 2 is where P2 lives, and step 3 is where the REFUSAL lives, and they are on different
-- tables ON PURPOSE. §4.1 law 1 forbids a CHECK from counting rows in another table, so the
-- cross-row fact is projected onto a scalar on the subject row and the CHECK is a plain-column
-- predicate over that scalar. PROJECT, then REFUSE. This file is the PROJECT source; 0027 is the
-- REFUSE site.
--
-- `carriage_one_open` — PARTIAL UNIQUE, AND IT CLOSES A REAL HOLE. Without it, the same (series,
-- doc) pair can be opened twice at two different commits, both with `closed_commit IS NULL`.
-- `open_token_count` then reads 2, closing one carriage takes it to 1, and the document still
-- cannot be superseded even though nothing carries the series any more — or, in the other
-- direction, a counter maintained by decrement goes to 0 while an open row remains and MI19 waves
-- the supersession through. Both are counting bugs that a partial unique index makes impossible
-- at the source: at most one OPEN carriage per (series, doc), any number of closed historical
-- ones. GT-14 confirmed partial UNIQUE indexes on this platform.
--
-- WHY `opened_commit` IS IN THE PRIMARY KEY. A document may carry a series, lose it, and carry it
-- again years later — that is an ordinary lifecycle for a procedure that was split and later
-- recombined. (series_id, doc_id) alone would collapse those into one row and destroy the history
-- of the gap. The opening commit makes each carriage episode its own row, permanently.
--
-- BOTH COMMIT POINTERS ARE FK'd. `opened_commit` and `closed_commit` are the evidence for "when",
-- and a carriage boundary that names a commit nobody can produce is not evidence. The closing
-- pointer is nullable and MATCH-SIMPLE-satisfied when NULL, so an open carriage needs no
-- placeholder.
--
-- `carriage_open (doc_id) WHERE closed_commit IS NULL` IS THE PROJECTION'S OWN INDEX. The counter
-- trigger asks exactly one question — "how many open carriages does this doc have" — on every
-- write to this table, so it gets a partial index keyed on precisely that predicate. A projection
-- trigger with an unindexed read is a projection trigger somebody will eventually delete for
-- being slow, and P2 columns do not survive being inconvenient.
--
-- NO `site_id` ON THIS TABLE, unlike almost everything else in the schema. It would be derivable
-- three ways (from the series, from the document, from either commit) and therefore forgeable in
-- three ways, and RLS scoping reaches this table through mainline.doc, which is where the tenancy
-- decision belongs. A denormalised scope token here would be a fourth authority on the same
-- question, which is one more than a scope token may have.
--
-- UNVERIFIED ON THIS MACHINE: no CockroachDB v26.2 was reachable when this band was authored, so
-- this statement has not been executed. Inline `WHERE` on an index definition is already relied
-- on by 0023 in the foundation band; adding UNIQUE to that inline partial form is the part that
-- is untested here. If v26.2 refuses it, the remediation is to move `carriage_one_open` into its
-- own `0048a_carriage_one_open.up.sql` as `CREATE UNIQUE INDEX … WHERE closed_commit IS NULL`.

CREATE TABLE mainline.carriage (
  series_id     UUID  NOT NULL,
  doc_id        UUID  NOT NULL,
  opened_commit BYTES NOT NULL,
  closed_commit BYTES NULL,     -- NULL ⇒ still carried. THIS is what MI19 counts.
  CONSTRAINT carriage_pk PRIMARY KEY (series_id, doc_id, opened_commit),
  CONSTRAINT fk_series FOREIGN KEY (series_id) REFERENCES mainline.control_series (series_id),
  CONSTRAINT fk_doc FOREIGN KEY (doc_id) REFERENCES mainline.doc (doc_id),
  CONSTRAINT fk_opened_commit FOREIGN KEY (opened_commit)
    REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT fk_closed_commit FOREIGN KEY (closed_commit)
    REFERENCES mainline.commit_obj (commit_id),
  UNIQUE INDEX carriage_one_open (series_id, doc_id) WHERE closed_commit IS NULL,
  INDEX carriage_open (doc_id) WHERE closed_commit IS NULL
);
