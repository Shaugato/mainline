-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0162_v_ledger_health.sql
-- CREATE VIEW mainline_audit.v_ledger_health — is the custody log admissible, and what is owed
--
-- MI: MI24, MI18
-- I: I16
-- COUNSEL-GATED: no
-- RATIONALE: `admissible` is the only column in the schema that means "an independent witness
--            in another trust domain has cosigned this checkpoint". Counting admissible AND
--            inadmissible checkpoints side by side is the honest form: a log that reports only
--            its admissible count is a log that hides the window in which it was not. `open_debt`
--            is the same honesty applied forward — a permit issued before its evidence reached
--            a cosigned checkpoint is a debt, and a debt nobody counts is a claim nobody can
--            falsify.
--
-- migration:  0162_v_ledger_health
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI24 — the ledger sequence is dense and fork-free.
--             MI18 — a recall runs only under an anchored, cosigned policy version; the
--                    anchoring target is a checkpoint counted here.
--             I16  — external witness: no checkpoint is admissible unless cosigned across
--                    ≥ k distinct trust domains including ≥ 1 adverse.
-- source:     ARCHITECTURE.md §17 (view definition) · §5.6 (ledger_checkpoint,
--             unwitnessed_debt) · §7.2, §7.5 · §9.1
-- requires:   0075 mainline.ledger_checkpoint · 0077 mainline.unwitnessed_debt
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THIS VIEW IS NOT THE VERIFICATION, AND MUST NEVER BE PRESENTED AS ONE
-- ─────────────────────────────────────────────────────────────────────────────
-- Everything here is the log's own account of itself, read out of the same
-- cluster the log lives in. An expert's first question about a self-hosted
-- tamper-evidence claim is exactly that, and the answer is not this view: it is
-- `trappoint-verify`, a ~100-line-dependency binary a stranger runs against the
-- published checkpoints and the S3 Object Lock COMPLIANCE copies, reproducing
-- the Merkle roots from the leaves without trusting anything we serve.
--
-- What this view is for is the OPERATIONAL question — is the sequencer keeping
-- up, are cosignatures arriving, is anything owed — asked over a transport that
-- an auditor's agent already has. Presenting it as evidence of integrity would
-- be presenting the accused's own summary of the accounts, and §11.7 forbids
-- exactly that class of claim.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY `tree_size` IS max() AND NOT count()
-- ─────────────────────────────────────────────────────────────────────────────
-- `ledger_checkpoint` is keyed `(site_code, tree_size)` and tree_size is the
-- RFC 6962 tree size at issuance, so max(tree_size) is the number of leaves the
-- log has committed to — the log's length. count(*) would be the number of
-- checkpoints ISSUED, which is a function of the 60-second anchoring cadence and
-- says nothing about the log. Reporting the cadence as the length is the kind of
-- number that survives into a deck and gets taken apart in a deposition.
--
-- Note also that tree_size = 0 is legal and meaningful: a log must be able to
-- prove it was empty. `max(tree_size) = 0` on a live site is therefore a real
-- state and not a missing-data artefact, which is why `checkpoints` is carried
-- beside it — the pair distinguishes "empty log, correctly attested" from
-- "no checkpoint has ever been issued here".
--
-- ─────────────────────────────────────────────────────────────────────────────
-- THE COMPLETENESS FLAG ON THIS VIEW
-- ─────────────────────────────────────────────────────────────────────────────
-- The band's uniform truncation contract is `group_count` + `rows_complete`.
-- This view adds `witness_complete`: false whenever the site holds any
-- inadmissible checkpoint or any undischarged debt. That is the ledger channel's
-- form of "the walk did not finish", and it is fail-closed in the same direction
-- as `ancestry_complete` elsewhere in the band — an absence reports false.

CREATE VIEW mainline_audit.v_ledger_health AS
  WITH g AS (
    SELECT c.site_code                                     AS site_code,
           max(c.tree_size)                                AS tree_size,
           count(*)                                        AS checkpoints,
           count(*) FILTER (WHERE c.admissible)            AS admissible_checkpoints,
           count(*) FILTER (WHERE NOT c.admissible)        AS inadmissible_checkpoints,
           count(*) FILTER (WHERE c.tsa_token IS NOT NULL) AS time_bounded_checkpoints,
           count(*) FILTER (WHERE c.s3_version IS NOT NULL) AS object_locked_checkpoints,
           max(c.issued_at)                                AS last_issued_at,
           count(DISTINCT c.canon_src_sha256)              AS canonicaliser_versions,
           -- Correlated, per site, exactly as §17 wrote it. Open debt is `discharged_tree_size
           -- IS NULL`: the permit was issued and its evidence has not yet reached a cosigned
           -- checkpoint. It is not an error; it is an amount owed, and it ages.
           (SELECT count(*)
              FROM mainline.unwitnessed_debt u
             WHERE u.site_code = c.site_code
               AND u.discharged_tree_size IS NULL)         AS open_debt,
           (SELECT min(u2.incurred_at)
              FROM mainline.unwitnessed_debt u2
             WHERE u2.site_code = c.site_code
               AND u2.discharged_tree_size IS NULL)        AS oldest_open_debt_at
      FROM mainline.ledger_checkpoint c
     GROUP BY c.site_code
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.site_code                 AS site_code,
         g.tree_size                 AS tree_size,
         g.checkpoints               AS checkpoints,
         g.admissible_checkpoints    AS admissible_checkpoints,
         g.inadmissible_checkpoints  AS inadmissible_checkpoints,
         g.time_bounded_checkpoints  AS time_bounded_checkpoints,
         g.object_locked_checkpoints AS object_locked_checkpoints,
         g.canonicaliser_versions    AS canonicaliser_versions,
         g.last_issued_at            AS last_issued_at,
         g.open_debt                 AS open_debt,
         g.oldest_open_debt_at       AS oldest_open_debt_at,
         (g.inadmissible_checkpoints = 0 AND g.open_debt = 0) AS witness_complete,
         t.group_count               AS group_count,
         (t.group_count <= 25)       AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.site_code
   LIMIT 25;
