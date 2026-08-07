-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI25
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: P2 forbids a gate-adjacent column with no authoritative source, and ARCHITECTURE §5 carries `site_id` on forty tables, `permit.site_role NAME` filled by `fn_site_role`, `ledger_intake.site_code` and `event_cue_coarse.tenant_id` with no table behind any of them; `site_role` is the RLS scope token, so a projection with no source is a scope token a writer can forge.
--
-- migration:  0021_site
-- band:       0001-0023 · dm-foundation
-- statements: 1
-- source:     docs/leads/datamodel.md DM-3 (NEW; not in ARCHITECTURE §5) · §11.3 (RLS) · §4.1 law 10
-- requires:   0002 CREATE SCHEMA mainline
-- seeds:      none. Sites are customer facts, and the test suite mints one per test as its
--             isolation primitive.
-- sqlstate:   23505 on site_code_unique / site_role_unique; 23514 on the shape CHECKs;
--             P0001 from the projection triggers in band 0130-0199 when a site row is absent
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS TABLE IS THE AUTHORITATIVE SOURCE FOR EVERY PROJECTED site_role, site_code AND tenant_id
-- IN THE SCHEMA. Nothing else may be. A trigger that writes one of those three columns onto a
-- subject row reads it FROM HERE and RAISEs P0001 when this table has no matching row — never
-- from the inserter, never from a session variable, never from a default.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHY IT EXISTS (DM-3). The adversarial review's two build-blocking findings were both "a
-- projection was trusted rather than enforced". `site_role` is the worst possible column to get
-- that wrong on: RLS policy expressions cannot contain subqueries (§4.1 law 10), so tenancy scope
-- is a denormalised role-name token compared as `site_role = CURRENT_USER`. If the writer supplies
-- the token, the writer chooses which tenant can see the row — and RLS degrades to an
-- application-cooperative control, which is worthless against exactly the adversary it exists to
-- constrain. Behind every such token there must be a row somebody provisioned.
--
-- THE FOUR COLUMNS, AND WHAT READS EACH:
--
--   site_id       the join key carried by ~40 tables, and the test suite's isolation primitive
--                 (one fresh site_id per test, xdist-safe against one long-lived cluster).
--   site_code     the LEDGER's partition key. `PRIMARY KEY (site_code, seq)` is what makes MI24 —
--                 the ledger sequence is dense and fork-free — a 23505 rather than a hope. Also
--                 the C-SPANN checkpoint prefix the recall band already reads (0112).
--   site_role     the RLS scope token, type NAME, compared to CURRENT_USER. NAME and not STRING
--                 because that is the type CURRENT_USER has, and a comparison across an implicit
--                 cast is a comparison a future release is entitled to change the semantics of.
--   tenant_id     CONSTANT per deployment, and the coarse-sweep prefix on `event_cue_coarse`.
--                 A C-SPANN vector index is used only if every prefix column is constrained to a
--                 specific value, so this column is the one that decides whether the coarse sweep
--                 is an index scan or a full scan — and 0042 currently takes it from the client,
--                 recorded there as an unclosed loop that THIS TABLE closes.
--   taxonomy_ver  the archival taxonomy generation the site's scopes were cut under. Bumping it
--                 is a re-cut of the LMB scope tree, not an edit.
--
-- THE SHAPE CONSTRAINTS ARE NOT COSMETIC. An unquoted SQL identifier folds to lower case, so
-- CURRENT_USER for a role created as `SITE_NORTH` is `site_north`. A `site_role` stored as
-- `SITE_NORTH` therefore matches nothing, and an RLS policy that matches nothing does not error —
-- it returns zero rows, silently, for every query, forever. A tenancy control that fails closed
-- and silent looks exactly like a tenancy control that works, right up until the day someone
-- notices a site has never seen its own data. `site_role_is_lower_case` refuses the row instead.
--
-- UNVERIFIED ON THIS MACHINE (honesty, per the build discipline): `lower()` inside a CHECK is
-- standard, immutable, and accepted by PostgreSQL, and nothing in CockroachDB's CHECK
-- documentation excludes an immutable builtin — but no CockroachDB v26.2 was reachable from the
-- machine this file was written on (no `cockroach` binary, no Docker daemon), so it has not been
-- executed. If v26.2 rejects it, the fix is to delete the two `*_lower_case` CONSTRAINT lines and
-- move the assertion into tests/integration/schema/test_mi_rls.py; nothing else in the band
-- depends on them.
--
-- `opened_at` DEFAULT now() is a convenience for the test fixture ONLY. For a real site it is the
-- operational commissioning date and the provisioning path supplies it explicitly; a row that
-- silently records "when we inserted the row" as "when the mine opened" is a small lie that a
-- retention calculation would later treat as a fact.

CREATE TABLE mainline.site (
  site_id      UUID        NOT NULL,
  site_code    STRING      NOT NULL,   -- ledger partition key: PRIMARY KEY (site_code, seq)
  site_role    NAME        NOT NULL,   -- RLS scope token: USING (site_role = CURRENT_USER)
  tenant_id    UUID        NOT NULL,   -- constant per deployment; the coarse-sweep vector prefix
  taxonomy_ver INT4        NOT NULL,
  opened_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT site_pk PRIMARY KEY (site_id),
  CONSTRAINT site_code_unique UNIQUE (site_code),
  CONSTRAINT site_role_unique UNIQUE (site_role),
  CONSTRAINT site_code_stated CHECK (site_code <> ''),
  CONSTRAINT site_code_is_lower_case CHECK (site_code = lower(site_code)),
  CONSTRAINT site_role_is_lower_case CHECK (site_role::STRING = lower(site_role::STRING)),
  CONSTRAINT taxonomy_ver_positive CHECK (taxonomy_ver >= 1)
);
