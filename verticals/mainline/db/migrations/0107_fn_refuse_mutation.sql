-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0107_fn_refuse_mutation.sql
-- CREATE FUNCTION mainline.fn_refuse_mutation — there is no legal mutation of an evidentiary row
--
-- MI: MI01
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: Revoked privileges are cluster state and a restore into a new cluster does not
--            carry them; an incident is exactly when somebody is granted more than they
--            should have; and the owner role can always grant itself anything. This trigger
--            travels with the schema, survives a restore, and is independent of both the
--            grant matrix and the row-level security policies, which is what makes append-
--            only a refusal of depth three rather than a promise. It carries no condition,
--            because an exception to append-only is not a narrower rule but a different
--            one, and the one table that needs it has its own function.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0106_fn_refuse_mutation.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- migration:  0107_fn_refuse_mutation
-- band:       0100-0109z · kernel/projection-triggers · RENDERED
-- statements: 1
-- invariants: MI01 — evidentiary tables are append-only
-- source:     ARCHITECTURE.md §5.11 item 9 · spec/invariants/I01-append-only.md ·
--             spec/custody/ledger-schema.md §3
-- requires:   nothing. It reads no relation and names no column, which is why it can be created
--             before every table it will later guard.
-- provides:   mainline.fn_refuse_mutation() — welded by 0128 and its companions
-- sqlstate:   P0001, always, with no path that returns
-- forward-only; no .down.sql and no .up.sql (MR-5).
--
-- ACYCLICITY. It raises. Trigger depth contributed: 0, by construction.

CREATE FUNCTION mainline.fn_refuse_mutation() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='P0001',
    MESSAGE='MAINLINE: this table is append-only; write a new row';
END $$;
