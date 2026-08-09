-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0151_v_cbm_ledger.sql
-- CREATE VIEW mainline_audit.v_cbm_ledger — the conservation law, readable over MCP in one call
--
-- MI: MI03, MI25, MI26
-- I: I02, I13
-- COUNSEL-GATED: no
-- RATIONALE: The refusals are in the write path and that is where they belong; this view is how
--            a person — an auditor, a regulator, a judge over an MCP connection — SEES the
--            arithmetic without being able to touch it. It is aggregate-first and hard-capped at
--            25 rows because the managed MCP surface caps a SELECT at 25 rows and a response at
--            10 KiB, and a view that silently returns the first 25 of 4,000 is a view that lies
--            by omission. `ledger_truncated` is the honest half: every row carries the total, so
--            a reader who sees 25 rows also sees whether 25 was all of them.
--
-- migration:  0151_v_cbm_ledger
-- domain:     algorithms
-- band:       0150-0154z · algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), which grants this
--             band to this domain exclusively; `0150` is `v_safe_direction_current` (W2).
--             ONE TENSION, RECORDED RATHER THAN RESOLVED SILENTLY: the band's `contents` string
--             reads "mainline.* business views" and this view is in `mainline_audit`. The
--             binding block at the end of docs/leads/algorithms.md names
--             `mainline_audit.v_cbm_ledger` in the list of this domain's unwritten objects and
--             says they "take their numbers from the three bands above" — of which this is the
--             only view band. The allocation is enforced by NUMBER and MODE (lint rule B), not
--             by schema, so `0151` is legal and owned; the description is the thing that is
--             imprecise, and correcting it is an edit to a file this worker does not own.
--             It is raised in this worker's cross-domain notes rather than performed here.
-- statements: 1  (the CREATE VIEW, and nothing else)
-- invariants: MI03 — the count this view reports.  MI25/MI26 — it reads the NEWEST generation
--             and says so.  I13 — truncation is disclosed, never silent.
-- source:     docs/leads/algorithms.md §5 · ARCHITECTURE.md §17 (MCP: one statement per call,
--             <= 25 rows, <= 10 KiB, no EXPLAIN ANALYZE) · §16.
-- requires:   0003 SCHEMA mainline_audit · 0049 mainline.identity_residue ·
--             0049c mainline.cbm_account
-- sqlstate:   none. This is a view; it refuses nothing and claims to refuse nothing.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHAT EACH COLUMN IS FOR, AND WHICH ONE IS THE EXHIBIT
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `balanced` IS A TAUTOLOGY AND IT IS REPORTED ANYWAY. `CONSTRAINT cbm_balances` refuses an
-- account that does not balance, so every row this view can possibly show has `balanced = true`.
-- That is not a defect in the view and it is not news dressed up as a finding — it is the claim,
-- stated in the form a reader can check for themselves: *the only accounts that exist are the
-- ones that balance.* A column that is constant BY CONSTRUCTION is worth more than a column
-- that happens to be constant today, and the difference is exactly what this project is about.
--
-- `accounting_stale` IS THE COLUMN THAT ACTUALLY MOVES. An account is append-only, so it
-- describes the world at the moment it was written; residue can be dispositioned or discovered
-- afterwards. This column compares the newest account's `residue_open` against the LIVE count of
-- distinct ancestors with an open residue row for the same commit. `true` means a merge citing
-- that commit is refused right now by `z_cbm_gate` with "blame accounting is stale for a cited
-- commit", and the remedy is one more account generation.
--
-- `live_residue_open` is beside it so the reader sees both numbers rather than a verdict. A
-- console that showed only the boolean would be asking to be trusted.
--
-- ── AGGREGATE-FIRST, AND WHY THE TOTALS ARE ON EVERY ROW ─────────────────────────────────────
-- `n_accounted_commits`, `n_obligations_inherited` and `n_obligations_open` are computed over
-- ALL newest-generation accounts, not over the 25 rows returned, and they are repeated on every
-- row. Repetition is deliberate: the MCP surface returns rows, not a result set with a header,
-- so a total that lived in its own row would be a row a truncating client could drop. A reader
-- who receives ONE row still receives the whole shape of the ledger.
--
-- `ledger_truncated` is `n_accounted_commits > 25`. It is the `ancestry_complete`-equivalent
-- flag: the same discipline the recall domain applies to a truncated ancestry walk, applied to
-- a truncated ledger. I13 — silence is logged; a partial answer that does not say it is partial
-- is the failure mode this whole design refuses elsewhere, and a view is not exempt.
--
-- ── ORDERING PUTS THE WORST FIRST ────────────────────────────────────────────────────────────
-- Stale accounts, then commits with the most open obligations, then most recently accounted. A
-- reader who can see only 25 rows should see the 25 that block something. Ordering by
-- `computed_at DESC` alone would show the busiest projector rather than the loudest problem.
--
-- ── SIZE, AND WHY THE TWO SUBSTRINGS ARE THERE ───────────────────────────────────────────────
-- 10 KiB over 25 rows is ~400 bytes per row. `commit_id` is rendered as the first 16 hex
-- characters of its sha256 — enough to identify a commit in a repository of any realistic size,
-- and 16 characters instead of 64. `wrote_as` and `projector_ver` are clipped to 32 characters
-- because a Lambda ARN or a build tag can be long enough to blow the budget on its own.
-- `tests/integration/algorithms/cbm/test_ledger_view.py` measures the real encoded size against
-- the real cap rather than trusting this arithmetic.
--
-- MEASURED, 2026-08-09, AND IT IS A CONSTRAINT ON THE RENDERER, NOT ON THIS VIEW. A full 25-row
-- result encodes to ~5 KiB as `{"columns": [...], "rows": [[...], ...]}` — column names once,
-- values as arrays, which is the shape a SQL tool over MCP returns — and to ~12.6 KiB as one
-- JSON OBJECT PER ROW, because the nineteen column names are then repeated 25 times and cost
-- roughly 11 KiB before a single value is written. Any console or MCP shim that serialises this
-- view as per-row objects WILL breach the 10 KiB cap and be truncated by the transport, and a
-- truncation the client performs is precisely the silent partial answer `ledger_truncated`
-- exists to prevent. Both sizes are asserted by the test so neither can drift unnoticed.
--
-- ── WHAT THIS VIEW DELIBERATELY DOES NOT SHOW ────────────────────────────────────────────────
-- No clause text, no ancestor identifiers, no person. I15 — no substrate row may characterise a
-- named human's conduct — and a ledger that named the ancestor clauses a projector failed to
-- account for would be one join away from naming who wrote them. The unit of this view is the
-- COMMIT and the counters over it; anyone entitled to the detail reads the underlying tables
-- through the policies that govern them.
--
-- ── UNVERIFIED ───────────────────────────────────────────────────────────────────────────────
-- RLS is not applied here and is not this domain's to apply: the `mainline_audit` policies live
-- in `dm-views-rls`'s band `0180`-`0198`. This view therefore inherits whatever the underlying
-- tables enforce, which is the correct default and not a claim of isolation.

CREATE VIEW mainline_audit.v_cbm_ledger AS
  WITH newest AS (
    SELECT DISTINCT ON (a.site_id, a.commit_id)
           a.site_id          AS site_id,
           a.commit_id        AS commit_id,
           a.account_gen      AS account_gen,
           a.inherited        AS inherited,
           a.carried          AS carried,
           a.split_carried    AS split_carried,
           a.merge_carried    AS merge_carried,
           a.residue_open     AS residue_open,
           a.residue_disposed AS residue_disposed,
           a.balanced         AS balanced,
           a.wrote_as         AS wrote_as,
           a.projector_ver    AS projector_ver,
           a.computed_at      AS computed_at
      FROM mainline.cbm_account a
     ORDER BY a.site_id, a.commit_id, a.account_gen DESC
  ),
  live AS (
    SELECT r.commit_id AS commit_id,
           count(DISTINCT r.ancestor_clause_uuid) AS live_open
      FROM mainline.identity_residue r
     WHERE r.disposition_id IS NULL
     GROUP BY r.commit_id
  ),
  tally AS (
    SELECT count(*)                          AS n_accounted_commits,
           coalesce(sum(n.inherited), 0)     AS n_obligations_inherited,
           coalesce(sum(n.residue_open), 0)  AS n_obligations_open
      FROM newest n
  )
  SELECT n.site_id                                            AS site_id,
         substring(encode(n.commit_id, 'hex'), 1, 16)         AS commit_hex,
         n.account_gen                                        AS account_gen,
         n.inherited                                          AS inherited,
         n.carried                                            AS carried,
         n.split_carried                                      AS split_carried,
         n.merge_carried                                      AS merge_carried,
         n.residue_open                                       AS residue_open,
         n.residue_disposed                                   AS residue_disposed,
         n.balanced                                           AS balanced,
         coalesce(l.live_open, 0)                             AS live_residue_open,
         (n.residue_open <> coalesce(l.live_open, 0))         AS accounting_stale,
         substring(n.wrote_as::STRING, 1, 32)                 AS wrote_as,
         substring(n.projector_ver, 1, 32)                    AS projector_ver,
         n.computed_at                                        AS computed_at,
         t.n_accounted_commits                                AS n_accounted_commits,
         t.n_obligations_inherited                            AS n_obligations_inherited,
         t.n_obligations_open                                 AS n_obligations_open,
         (t.n_accounted_commits > 25)                         AS ledger_truncated
    FROM newest n
    LEFT JOIN live l ON l.commit_id = n.commit_id
    CROSS JOIN tally t
   ORDER BY (n.residue_open <> coalesce(l.live_open, 0)) DESC,
            n.residue_open DESC,
            n.computed_at DESC
   LIMIT 25;
