-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI11
-- I: I10
-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
-- RATIONALE: The conservative reading of G0 is not a column, a flag or a policy row — it is the
--            ABSENCE of three cells from the clearance lattice, and absence is the one thing a
--            schema cannot show you. This statement makes it visible: it returns NOTHING while
--            the reading holds, and one row per deviation the moment it does not. An empty
--            result set is the assertion.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS IS NOT A MIGRATION. It has no number, `discover()` never sees it, and it is never
-- applied. It is READ-ONLY — a single `SELECT` with no side effects — and it is therefore safe
-- to run against production, against the demo cluster, and from a read-only MCP session.
--
-- Where it belongs: verticals/mainline/db/ext/disposition_ext/, the counsel-gated extension
-- point (DM-17). Its filename carries a SECOND DOT on purpose, which is legal here and would be
-- fatal one directory over: inside `migrations/` a second dot yields a stem `_VERSION_RE`
-- rejects and makes `trappoint migrate` refuse the ENTIRE directory (MR-5, measured). Capability
-- and policy variants live under `db/ext/<topic>/` for exactly that reason.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHAT IT CHECKS, AND WHY BOTH ARMS ARE NEEDED.
--
--   'cell_opened'   — one of the three deliberately absent cells now EXISTS. This is the
--                     deviation that matters: the composite foreign key named `fk_clearance` on
--                     BOTH `mainline.disposition` and `mainline.carried_disposition` points at
--                     (virulence, kind), so the instant a row appears, signing and carrying that
--                     verdict stop being `23503` and start being legal — for every writer,
--                     silently, with no code change anywhere. That is the correct mechanism
--                     (opening a cell SHOULD be a data amendment with a named approver and a
--                     bumped policy_version, not a pull request) and it is precisely why it must
--                     be observable.
--
--   'cardinality'   — the lattice no longer holds exactly 21 of its 24 cells. Catches the
--                     opposite drift: a cell REMOVED rather than added, which does not open a
--                     gate but does silently strip a legal verdict from operators who need one,
--                     and would present in the field as "the sign button stopped working".
--
-- Running it:
--
--     cockroach sql --url "$DSN" \
--       -f verticals/mainline/db/ext/disposition_ext/clearance_legal.conservative.sql
--
-- Exit reading: ZERO ROWS means the conservative reading of ADR 0001 is intact. ANY ROW means
-- the shipped lattice no longer encodes it, and `disposition_ext.toml` must be amended to say
-- so — with `advice_reference`, `answered_at` and `answered_by` filled in, because a lattice
-- that has moved without an advice reference is an undocumented legal decision.
--
-- The expected set below is duplicated in `disposition_ext.toml` under `[disposition]
-- absent_cells` and in `README.md`. Three copies is deliberate: this one is EXECUTABLE, the TOML
-- one is MACHINE-READABLE, and the README one is the sentence a human quotes. The schema test
-- `tests/integration/schema/test_mi_disposition.py` asserts all three agree, so a copy that
-- drifts is a red test rather than a discovered surprise.

SELECT
    'cell_opened'                              AS finding,
    expected.virulence::STRING                 AS virulence,
    expected.kind::STRING                      AS kind,
    'this cell is deliberately absent under the conservative reading of G0 '
      || '(docs/adr/0001-g0-counsel.md) and it now EXISTS, so signing and carrying it '
      || 'are legal for every writer'          AS detail
  FROM (
    VALUES
      ('blood_fatal'::mainline.virulence_class, 'mechanism_absent'::mainline.disposition_kind),
      ('blood_fatal'::mainline.virulence_class, 'accept_residual'::mainline.disposition_kind),
      ('blood_major'::mainline.virulence_class, 'accept_residual'::mainline.disposition_kind)
  ) AS expected (virulence, kind)
  JOIN mainline.clearance_legal AS actual
    ON actual.virulence = expected.virulence
   AND actual.kind = expected.kind
UNION ALL
SELECT
    'cardinality'                              AS finding,
    '-'                                        AS virulence,
    '-'                                        AS kind,
    'the clearance lattice holds ' || count(*)::STRING || ' cells; the conservative reading '
      || 'seeds exactly 21 of the 24 (4 virulence bands x 6 disposition kinds)'
                                               AS detail
  FROM mainline.clearance_legal
 HAVING count(*) <> 21;
