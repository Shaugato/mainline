-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI18
-- I: I16, I13
-- COUNSEL-GATED: no
-- RATIONALE: MAINLINE NEVER BLOCKS WORK ON PAPERWORK. When the witness network is unreachable the
-- permit still merges — refusing to let people work because a cosigner in another company is down
-- would be a safety system that makes the site less safe, and it would be switched off within a
-- month. What happens instead is that the merge INCURS A DEBT, and no later checkpoint is
-- admissible while a debt is open. Going dark stays possible and SELF-REPORTS, which is the only
-- version of this trade-off that a regulator and an operations manager can both live with.
--
-- migration:  0077_unwitnessed_debt
-- band:       0072-0079 · cu-ledger-ddl (custody) · see OWNERSHIP note in 0072
-- statements: 1
-- source:     ARCHITECTURE.md §5.6 (verbatim shape) and its witness-diversity paragraph ·
--             §18 slot 0077 · spec/custody/ledger-schema.md §3 (the ONE permitted UPDATE) ·
--             spec/wire/checkpoint.md §5.3 · docs/leads/custody.md §6 risk 1, worker 9
-- requires:   0021 mainline.site · 0050 mainline.permit · 0075 mainline.ledger_checkpoint
-- owes:       `fn_refuse_mutation` on this table, band 0130-0199, carrying THE ONLY UPDATE
--             CARVE-OUT IN THE CUSTODY SURFACE — see the DISCHARGE section below, which states
--             the exact predicate that trigger must implement.
-- grants:     the three foreign keys require `SELECT ON mainline.site`, `SELECT ON
--             mainline.permit` and `SELECT ON mainline.ledger_checkpoint` for every role that
--             inserts here — see the MEASURED PLATFORM FACT block in 0072. `fk_permit` is
--             verbatim from ARCHITECTURE.md §5.6, so this gap in GRANTS.yaml predates any
--             decision taken in this band.
-- sqlstate:   23503 on fk_site / fk_permit / fk_discharge · 23514 on discharge_non_negative ·
--             P0001 from the discharge guard once it lands
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- DISCHARGE — the single exception to append-only in the entire custody surface, and its bounds.
--
-- `spec/custody/ledger-schema.md` §3 is normative and narrow: `discharged_tree_size` is NULL until
-- a RETRO-COSIGNED checkpoint discharges the debt, and its UPDATE is permitted
--
--     * on that column ONLY,
--     * only from NULL,
--     * and only to a `tree_size` that EXISTS in `mainline.ledger_checkpoint`.
--
-- The third bound is enforced HERE, structurally, by `fk_discharge` — a composite foreign key on
-- `(site_code, discharged_tree_size)` onto the checkpoint's primary key. Under the SQL default
-- MATCH SIMPLE, a row whose `discharged_tree_size` is NULL satisfies the constraint vacuously, so
-- an open debt is legal and a discharge naming a checkpoint that does not exist is 23503. The
-- first two bounds are a trigger's job (band 0130-0199) because they are statements about a
-- TRANSITION, and a CHECK cannot see OLD.
--
-- Why an exception exists at all, when §3 spends a paragraph refusing to make any: discharge is a
-- fact about the world ARRIVING LATE, not a rewrite of what was recorded. The debt was genuinely
-- incurred; the cosignature genuinely arrived afterwards. Recording that as a new row and leaving
-- the old one open would make the open-debt count permanently wrong, which is worse than the
-- carve-out, because the open-debt count is what gates admissibility.
--
-- The trigger must ALSO refuse NULL → NULL and value → value as no-ops rather than accepting them
-- silently: an UPDATE that changes nothing on an append-only table is still an UPDATE, and the
-- first thing an adversary does with a permitted UPDATE path is find out how wide it is.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHY THERE IS NO UNIQUE INDEX MAKING DEBT ONE-PER-PERMIT. It is tempting: MI09 gives one merge
-- per permit, so one debt per permit looks like a free invariant. It is not free — it is a
-- REFUSAL, and a refusal on this table would block a merge for a bookkeeping reason, which is the
-- one thing this table exists to avoid. Duplicate debt rows for one permit inflate the open-debt
-- count and therefore delay admissibility; that failure is conservative, self-announcing and
-- reconcilable. A wrong UNIQUE here would stop work on a mine site. The reconciliation patrol
-- (`mainline-custody-patrol`) is the right instrument, and this is recorded so the omission reads
-- as a decision rather than an oversight.
--
-- `by_site_open` IS A PARTIAL INDEX BECAUSE THE ONLY QUESTION EVER ASKED IS "WHAT IS STILL OPEN".
-- Discharged debts are history and are never on the hot path: admissibility asks whether any debt
-- for this site is open, and the patrol asks which ones and since when. The index is over exactly
-- those rows, so it stays small while the table grows monotonically forever.
--
-- `incurred_at` IS A LOCAL CLOCK. It is used to age open debt for the operations dashboard and it
-- is not evidence of when anything happened. As everywhere else in this band: the defensible
-- statements about time are the bracketed ones on the checkpoint.
--
-- NO ROW-LEVEL TTL ON THIS TABLE, EVER. See 0072. A debt that expires by itself is the exact
-- outcome the mechanism exists to prevent.

CREATE TABLE mainline.unwitnessed_debt (
  debt_id              UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_code            STRING      NOT NULL,
  permit_id            UUID        NOT NULL,
  incurred_at          TIMESTAMPTZ NOT NULL DEFAULT now(),   -- local clock; ages the debt
  discharged_tree_size INT8        NULL,   -- NULL = open. THE one updatable column (§3)
  CONSTRAINT unwitnessed_debt_pkey PRIMARY KEY (debt_id),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT fk_permit FOREIGN KEY (permit_id) REFERENCES mainline.permit (permit_id),
  CONSTRAINT fk_discharge FOREIGN KEY (site_code, discharged_tree_size)
    REFERENCES mainline.ledger_checkpoint (site_code, tree_size),
  CONSTRAINT discharge_non_negative
    CHECK (discharged_tree_size IS NULL OR discharged_tree_size >= 0),
  INDEX by_site_open (site_code, incurred_at ASC) WHERE discharged_tree_size IS NULL,
  INDEX by_permit (permit_id)
);
