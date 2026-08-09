-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0070_carried_disposition_use.sql
-- CREATE TABLE mainline.carried_disposition_use — every reuse is a row, and the row can be refused
--
-- MI: MI28, MI11, MI01
-- I: I12, I10, I01
-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
-- RATIONALE: A carried disposition clears nothing by itself; it is only ever consumed here, and this is therefore the table where the reuse can be REFUSED rather than merely recorded. Three projected scalars turn three cross-row facts into plain-column CHECKs: a signature issued at one virulence may not clear an obligation of a higher one, a signature that had been revoked may not be spent, and a signature may not be spent after its window closes. That is the TRAPPOINT idiom applied to the one mechanism in the schema whose whole purpose is to reduce the number of times a human looks.
--
-- migration:  0070_carried_disposition_use
-- band:       0069-0070z · datamodel/ex-dm-disposition · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.5 (shape, plus five projected columns and five constraints
--             argued below) · findings S12, S18 · §16 MI28, MI11, MI01 ·
--             docs/leads/datamodel.md P2, DM-4, DM-10, DM-17
-- requires:   0058 mainline.blocking_check (RENDERED) · 0069 mainline.carried_disposition
-- projects:   carried_virulence, carried_virulence_rank, carried_expires_at, carried_live <=
--             mainline.carried_disposition; check_virulence, check_virulence_rank <=
--             mainline.blocking_check. Banners below; the trigger is band 0140-0149z and DOES
--             NOT EXIST YET.
-- sqlstate:   23503 on fk_use_carried / fk_use_check; 23514 on carried_covers_check /
--             used_within_window / carried_was_live / carried_rank_agrees / check_rank_agrees;
--             23505 on the primary key; P0001 from the append-only trigger
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY THE ENFORCEMENT IS HERE AND NOT ON 0069.
--
-- `carried_disposition` is a SIGNATURE. This is a SPENDING of it. Every property that matters is
-- a relation between the signature and the obligation it is being spent on, and none of those
-- relations exist at the moment the signature is written:
--
--   is the signature strong enough for THIS obligation?   both rows required
--   was the signature still alive when it was spent?      both rows and the clock required
--   was it spent inside its window?                       both rows and the clock required
--
-- So the refusals live on the row that has both ends. Each one follows the kernel idiom exactly:
-- PROJECT the cross-row fact onto a scalar column of the row being written, from an authoritative
-- table and never from the inserter, then REFUSE with a plain-column CHECK that every writer
-- meets — the console, the gate service, an agent, a DBA at 3am, and the MCP insert path.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- @projects   carried_disposition_use.carried_virulence, carried_disposition_use.carried_virulence_rank, carried_disposition_use.carried_expires_at, carried_disposition_use.carried_live
-- @authority  mainline.carried_disposition (carried_id) <= NEW (carried_id)
-- @on_missing raise
--
-- @projects   carried_disposition_use.check_virulence, carried_disposition_use.check_virulence_rank
-- @authority  mainline.blocking_check (check_id) <= NEW (check_id)
-- @on_missing raise
--
-- ── WHY THERE IS A RANK *AND* AN ENUM FOR EACH VIRULENCE ──────────────────────────────────────
-- `mainline.virulence_class` is an ENUM and the comparison this table needs is an ORDERING —
-- "at least as severe as". CockroachDB's published ENUM documentation covers casting and
-- equality; it does not state that `<`/`>=` order values by declaration position, and NO
-- CockroachDB v26.2 was reachable from the authoring machine to measure it. A safety refusal must
-- not rest on an unmeasured ordering, so the comparison is done on an INT2 BAND and the enum is
-- kept beside it as the exhibit — a reader of this row sees 'blood_fatal', not 3.
--
-- The two are prevented from disagreeing by `carried_rank_agrees` / `check_rank_agrees`, which
-- pin the band to the enum with a CASE over the documented enum-to-STRING cast. Writing rank 0
-- beside 'blood_fatal' to sneak a routine signature onto a fatality-written control is a 23514
-- naming the constraint, not a subtle success. Under DM-4 this is legal in a CHECK: a CASE
-- expression and a cast are neither a JSONB operator, a subquery, `now()`, nor a function of
-- undocumented immutability.
--
-- IF THE ENUM ORDERING IS LATER MEASURED AND HOLDS, the two rank columns and their two agreement
-- constraints can be dropped and `carried_covers_check` rewritten over the enums directly. That
-- is a strictly smaller schema and a one-file change. It is not taken now because "probably
-- ordered" is not a basis on which to refuse — or fail to refuse — a fatality-written control.
--
-- ── `carried_live` IS ALWAYS TRUE IN A STORED ROW, AND THAT IS THE POINT ──────────────────────
-- It is the same shape as `disposition.user_verified` and `uv_required` on 0066: a projected
-- boolean whose only legal value is `true`, so that the ILLEGAL case is unrepresentable rather
-- than merely reportable. The trigger reads `carried_disposition.revoked_at` and writes
-- `carried_live = (revoked_at IS NULL)`; a spend against a revoked signature is then a 23514
-- naming `carried_was_live`, with the constraint name available to the conformance corpus as an
-- exhibit (DM-10). A nullable `carried_revoked_at` column would have carried the same fact and
-- refused nothing.
--
-- A REVOCATION THAT ARRIVES *AFTER* A USE DOES NOT INVALIDATE THIS ROW, and must not. The use
-- happened; deleting or amending the record of it would be the destruction of evidence this
-- substrate exists to detect. What must happen instead is that the blocking check RE-OPENS,
-- `permit.open_blocking` rises and `gate_epoch` bumps — which, for a permit already issued, the
-- epoch pin (MI07) refuses outright, forcing the suspend-and-fork path. That cascade is the
-- revocation trigger's job in band 0140-0149z.
--
-- ── `used_within_window` IS A SEPARATE REFUSAL FROM `carried_was_live`, DELIBERATELY ──────────
-- Revocation is an ACT (somebody or something called the lease); expiry is the CLOCK running out.
-- They are different facts about the world and they get different constraint names, because the
-- name is the courtroom exhibit and "this signature had been revoked" and "this signature had
-- expired" are different sentences. `used_within_window` also compares two columns OF THE ROW
-- BEING WRITTEN, so it holds even if the trigger's definition of liveness ever drifts.
--
-- ── APPEND-ONLY (MI01) ────────────────────────────────────────────────────────────────────────
-- Nothing here is ever amended. §6's list of tables carrying `fn_refuse_mutation` predates the
-- S18 rename and does not name this table; it should, and the trigger belongs to band 0140-0149z.
-- UNTIL IT LANDS THIS TABLE IS MUTABLE BY ANY WRITER WITH THE GRANT. Stated, not assumed (PL-2).
--
-- ── THE PRIMARY KEY IS (carried_id, check_id), FROM §5.5 ──────────────────────────────────────
-- One carried disposition is spent at most once against any one obligation. A second spend is a
-- 23505 rather than a second row, because two spends of one signature against one check is not
-- two facts — it is one fact recorded twice, and it would double whatever the console counts.
--
-- VERIFIED 2026-08-10 against CockroachDB CCL v26.2.5 (local single node, insecure, 26257). The
-- statement applies — including the enum-to-STRING cast inside a CASE inside a CHECK, which is
-- the construct the two `*_rank_agrees` constraints depend on — and all four refusals fire by
-- name with SQLSTATE 23514:
--
--   * a rank-0 'routine' signature against a rank-3 'blood_fatal' obligation names
--     `carried_covers_check`;
--   * rank 3 written beside the enum 'routine' names `carried_rank_agrees`, so the rank is not
--     independently forgeable and the coverage refusal above is not decorative;
--   * `carried_live = false` names `carried_was_live`;
--   * a `carried_expires_at` in the past names `used_within_window`.
--
-- And the mechanism permits what it exists to make safe: a covering, live, in-window spend
-- INSERTS, and a second spend of the same signature against the same obligation is 23505.
--
-- The ENUM-ORDERING QUESTION REMAINS OPEN AND IS STILL NOT DEPENDED ON. This run measured that
-- the cast and the CASE work; it did NOT measure whether `<`/`>=` order enum values by
-- declaration position, because nothing here asks that question. If someone measures it later and
-- it holds, the simplification described above becomes available.
--
-- Evidence: tests/integration/schema/test_mi_boundary_override.py, the carried-use cases.

CREATE TABLE mainline.carried_disposition_use (
  carried_id            UUID NOT NULL,
  check_id              UUID NOT NULL,
  used_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- ▼ PROJECTED from mainline.carried_disposition. Trigger-written, never supplied.
  carried_virulence     mainline.virulence_class NOT NULL,   -- the exhibit
  carried_virulence_rank INT2 NOT NULL,                      -- the comparable; see the header
  carried_expires_at    TIMESTAMPTZ NOT NULL,
  carried_live          BOOL NOT NULL,   -- (revoked_at IS NULL) at the moment of the spend
  -- ▲
  -- ▼ PROJECTED from mainline.blocking_check, which itself projects from the blame closure (S1).
  check_virulence       mainline.virulence_class NOT NULL,
  check_virulence_rank  INT2 NOT NULL,
  -- ▲
  CONSTRAINT carried_disposition_use_pk PRIMARY KEY (carried_id, check_id),
  CONSTRAINT fk_use_carried FOREIGN KEY (carried_id)
    REFERENCES mainline.carried_disposition (carried_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_use_check FOREIGN KEY (check_id)
    REFERENCES mainline.blocking_check (check_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,

  -- THE COVERAGE REFUSAL. A signature issued at one virulence may not clear an obligation of a
  -- higher one. This is what makes understating virulence on 0069 self-punishing.
  CONSTRAINT carried_covers_check CHECK (carried_virulence_rank >= check_virulence_rank),
  -- THE LIVENESS REFUSAL. A revoked signature cannot be spent. Always true in a stored row.
  CONSTRAINT carried_was_live CHECK (carried_live = true),
  -- THE WINDOW REFUSAL. Distinct from revocation: the clock, not an act.
  CONSTRAINT used_within_window CHECK (used_at <= carried_expires_at),

  -- The band and the enum may not disagree. Without these two, the rank is forgeable and the
  -- coverage refusal above is decorative.
  CONSTRAINT carried_rank_agrees CHECK (carried_virulence_rank =
    CASE carried_virulence::STRING
      WHEN 'routine'     THEN 0
      WHEN 'serious'     THEN 1
      WHEN 'blood_major' THEN 2
      WHEN 'blood_fatal' THEN 3
    END),
  CONSTRAINT check_rank_agrees CHECK (check_virulence_rank =
    CASE check_virulence::STRING
      WHEN 'routine'     THEN 0
      WHEN 'serious'     THEN 1
      WHEN 'blood_major' THEN 2
      WHEN 'blood_fatal' THEN 3
    END),
  CONSTRAINT use_rank_range CHECK (carried_virulence_rank BETWEEN 0 AND 3
                               AND check_virulence_rank BETWEEN 0 AND 3),
  -- "Which carried signature cleared this obligation" — the primary key answers the converse.
  INDEX by_check (check_id, carried_id)
);
