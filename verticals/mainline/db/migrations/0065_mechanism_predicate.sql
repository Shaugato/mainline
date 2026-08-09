-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI28, MI12
-- I: I12, I10
-- COUNSEL-GATED: no
-- RATIONALE: A `mechanism_absent` disposition cannot be prose. It binds a machine-checkable predicate over the site's OWN registers — "this site operates no vessel in hazard class X" — plus the signer's stated probability that it holds throughout a BOUNDED window. An unquantified mechanism_absent is not a representable state, and an unfalsifiable one is worse than a signature because it wears the shape of evidence. This table is the lease: a changefeed watches the declared registers, and when the predicate falsifies the disposition is revoked automatically, the check re-opens, gate_epoch bumps, and the revocation is timestamped BEFORE whatever happens next.
--
-- migration:  0065_mechanism_predicate
-- band:       0065-0065z · datamodel/ex-dm-gate · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). The band's three
--             files are this table, its watch-set index (0065a) and predicate_revocation (0065b),
--             which is the MR-5 multi-statement slot: one logical object, three statements,
--             because CockroachDB DDL is not transactional across statements.
-- statements: 1
-- source:     ARCHITECTURE.md §5.5 "Falsifiable mechanism_absent and its automatic revocation
--             (M8)" · finding S12 · §16 MI28 · demo beat 4 (M8 DEFEATER LEASE, correction S3)
-- requires:   0001a CREATE SCHEMA mainline (RENDERED)
-- projects:   nothing supplied by a client survives in `term_count`, which the SERVER computes.
--             `state` is moved from 'holding' by the revocation trigger in band 0140-0149z.
-- sqlstate:   23514 on predicate_bounded / non_trivial / watch_set_nonempty /
--             p_holds_is_a_probability / predicate_state_closed / compiled_sha256_is_a_digest;
--             23505 on the primary key
-- exhibits:   spec R-3 (Exhibit Uniqueness) requires a refusal-bearing name to be unique across
--             the WHOLE schema, so the S12 window constraint is `predicate_bounded` and not
--             `bounded` — the spec names this mirror set explicitly
--             (`bounded` / `carried_bounded` / `predicate_bounded`), and `state_closed` is
--             `predicate_state_closed` because `mainline.doc` (0027) already owns `state_closed`.
--             The exhibit name alone must identify the refusal without a qualifying table.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE EXHIBIT THIS TABLE EXISTS TO INVERT.
--
--   WITHOUT IT   "He signed the hazard away and eleven months later a man died."
--   WITH IT      "He signed under a lease the firm could call. It called itself at 04:12 on the
--                 9th, before anything happened. Here is the register row that falsified it, the
--                 transition it forced, and the three permits it re-blocked."
--
-- That inversion is worth nothing if the lease can be written so that it can never be called. The
-- three constraints below are each a way of writing an uncallable lease, closed by name.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- 1 · `watch_set_nonempty` — A PREDICATE WITH NO WATCH SET CAN NEVER BE FALSIFIED.
--
-- `registers` names the register tables whose contents can make this predicate false. An empty
-- array is a predicate nothing observes: the changefeed subscribes to nothing, no signal ever
-- routes to it, and it holds until its horizon no matter what happens on the plant. That is a
-- permanent waiver wearing the costume of a falsifiable claim, and it is one empty literal away
-- from being the default.
--
-- WRITTEN AS `coalesce(array_length(registers, 1), 0) >= 1` AND NOT AS `array_length(registers,
-- 1) >= 1`, AND THE DIFFERENCE IS THE WHOLE CONSTRAINT. `array_length` of an EMPTY array is NULL,
-- not 0. A `CHECK` whose expression evaluates to NULL PASSES — that is SQL's three-valued logic
-- and it is not negotiable. So the naive form admits exactly the row it was written to refuse,
-- silently, on every writer, forever. The coalesce is not defensive style; without it this
-- constraint is decorative.
--
-- 2 · `non_trivial` — A PREDICATE WITH NO TERMS IS THE CONSTANT `true`.
--
-- §5.5 writes this as `CHECK (jsonb_array_length(ast->'terms') >= 1)`, and DM-4 forbids a JSONB
-- operator inside a CHECK expression across this whole schema. The rule is not stylistic: it
-- keeps every gate-adjacent CHECK to a plain-column comparison whose immutability and error
-- behaviour are obvious to a reader, and it removes the GT-13-class dependency from the critical
-- path. So the count moves OFF the CHECK and INTO the row, as a STORED generated column that the
-- SERVER computes from `ast`. The inserter cannot choose `term_count`, the CHECK reads a plain
-- INT4, and the refusal names `non_trivial` exactly as the corpus expects.
--
-- The `CASE`/`jsonb_typeof` wrapper handles the second shape of the same attack. `jsonb_array_
-- length` applied to a non-array RAISES rather than returning NULL, which would refuse the write
-- with an error class nobody modelled and no constraint name attached — a refusal that is
-- correct and useless. Mapping "not an array" to 0 turns `{"terms": "none"}` and `{}` and
-- `{"terms": []}` into the SAME 23514 naming `non_trivial`, which is the exhibit.
--
-- 3 · `predicate_bounded` (finding S12, MI28) — BOUNDED MEANS BOUNDED, NOT MERELY PRESENT.
--
-- `horizon_at IS NOT NULL` admits a lease expiring in the year 3000. Both halves are required:
-- the window must be non-empty (`horizon_at > opened_at`) and it must be shorter than a year.
-- Neither term references `now()`; both operands are columns of the row being written, which is
-- what keeps this a plain-column CHECK under §4 constraint 5.
--
-- `p_holds` IS STRICTLY BETWEEN 0 AND 1, AND THE STRICTNESS IS THE POINT (M8/M10). A signer who
-- writes 1.0 is claiming certainty, which no proper scoring rule can ever penalise and which
-- therefore costs nothing to assert; 0.0 is a signer certifying the mechanism is present while
-- signing that it is absent. Both ends are excluded so that every recorded probability is a
-- number the signer can be scored against later.
--
-- `site_id` — authoritative source `mainline.site` (DM-3); no FK, for the reason stated in 0054.
--
-- `state` IS THE ONE MUTABLE COLUMN and it moves 'holding' -> 'revoked' | 'expired' only. This
-- table is deliberately NOT in `fn_refuse_mutation`'s append-only list (§6), because calling the
-- lease IS an update; what makes that honest is that the CALL is evidenced by an append-only row
-- in `predicate_revocation` (0065b). The guard that refuses any other column change, and refuses
-- a move back to 'holding', is a BEFORE UPDATE trigger in band 0140-0149z (dm-functions-triggers)
-- and it does not exist yet. UNTIL IT LANDS, `state` IS CLIENT-MUTABLE AND THIS TABLE IS NOT
-- GATE-SAFE ON ITS OWN. Said here rather than discovered later.
--
-- VERIFIED 2026-08-10 against CockroachDB CCL v26.2.5 (local single node, insecure, 26257). The
-- two constructs that carried real risk both hold, and each of the three uncallable-lease forms
-- is refused by name:
--
--   * the STORED generated column over `jsonb_typeof` / `jsonb_array_length` / `CASE` is ACCEPTED
--     (the ground truth recorded STORED-with-`digest()` as PASS, F3, but not this expression) and
--     a well-formed predicate reads back `term_count = 1`;
--   * `registers = '{}'` is refused with SQLSTATE 23514 naming `watch_set_nonempty` — the
--     coalesce is doing the work, and without it this row inserts;
--   * `{"terms": []}` and `{}` are both refused naming `non_trivial`;
--   * `{"terms": "none"}` is refused naming `non_trivial` TOO, rather than raising an
--     unmodelled error class — the `CASE`/`jsonb_typeof` wrapper does what it was written for;
--   * a 400-day horizon and a horizon before `opened_at` are both refused naming `predicate_bounded`;
--   * `p_holds` of 1.0 and of 0.0 are both refused naming `p_holds_is_a_probability`.
--
-- The DM-5 fallback is therefore NOT taken. Had the generated column been refused, it would have
-- cost one file — `term_count INT4 NOT NULL` written by a BEFORE INSERT trigger in band
-- 0140-0149z, `non_trivial` unchanged — because the tests assert the BEHAVIOUR, never the
-- mechanism. Evidence: tests/integration/schema/test_mi_boundary_override.py, the lease cases.

CREATE TABLE mainline.mechanism_predicate (
  predicate_id    UUID     NOT NULL DEFAULT gen_random_uuid(),
  site_id         UUID     NOT NULL,   -- authoritative source: mainline.site (DM-3); no FK
  ast             JSONB    NOT NULL,   -- compiled boolean over site registers / config
  -- SERVER-COMPUTED. The inserter cannot choose it, so `non_trivial` below is a plain-column
  -- comparison and DM-4 holds. Non-array and absent `terms` both map to 0, not to an error.
  term_count      INT4     AS (coalesce(
                       jsonb_array_length(
                         CASE WHEN jsonb_typeof(ast->'terms') = 'array'
                              THEN ast->'terms' ELSE NULL END), 0)) STORED,
  registers       STRING[] NOT NULL,   -- the WATCH SET: which register tables falsify it
  compiled_sha256 BYTES    NOT NULL,
  opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  horizon_at      TIMESTAMPTZ NOT NULL,
  p_holds         FLOAT8   NOT NULL,   -- proper-scored (M8/M10); strictly inside (0, 1)
  state           STRING   NOT NULL DEFAULT 'holding',
  CONSTRAINT mechanism_predicate_pk PRIMARY KEY (predicate_id),
  -- An empty watch set is a lease nobody can call. `coalesce` because array_length of an empty
  -- array is NULL and a NULL CHECK PASSES. See the header.
  CONSTRAINT watch_set_nonempty CHECK (coalesce(array_length(registers, 1), 0) >= 1),
  -- No terms is the constant `true`. Counted by the server; compared as a plain INT4 (DM-4).
  CONSTRAINT non_trivial CHECK (term_count >= 1),
  -- S12 / MI28: bounded, not merely present.
  CONSTRAINT predicate_bounded CHECK (horizon_at > opened_at
                            AND horizon_at <= opened_at + INTERVAL '365 days'),
  CONSTRAINT p_holds_is_a_probability CHECK (p_holds > 0 AND p_holds < 1),
  CONSTRAINT predicate_state_closed CHECK (state IN ('holding', 'revoked', 'expired')),
  CONSTRAINT compiled_sha256_is_a_digest CHECK (length(compiled_sha256) = 32),
  -- The expiry sweeper's read path: holding predicates at this site, oldest horizon first.
  INDEX by_horizon (site_id, state, horizon_at)
);
