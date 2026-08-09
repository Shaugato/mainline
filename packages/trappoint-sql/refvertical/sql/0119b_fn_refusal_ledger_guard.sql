-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0119b_fn_refusal_ledger_guard.sql
-- CREATE FUNCTION trappoint_ref.fn_refusal_ledger_guard — append-only, and the allegation firewall as a structural check
--
-- MI: MI01
-- I: I01, I14, I15
-- COUNSEL-GATED: no
-- RATIONALE: The refusal ledger is the record of decisions the gate made, so a row that can
--            be edited records nothing. This guard refuses UPDATE and DELETE
--            unconditionally and, on INSERT, refuses a payload whose reason set is not an
--            array of modelled facts or whose atoms carry a key outside the closed
--            vocabulary. That last one is invariant I15 enforced structurally rather than
--            by regular expression: an unknown key is exactly where a score characterising
--            a named human would arrive, and the wire schema closes every atom with
--            additionalProperties false for the same reason.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0119a_fn_explain_refusal.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- WHAT IS HERE AND WHAT IS A CHECK, and the rule that decides. Anything expressible over
-- the row's own columns is a plain-column CHECK on the table (0071c), because a CHECK
-- refuses for every writer forever and needs no trigger to be enabled. What is left is
-- exactly three things a CHECK cannot say: the operation is an UPDATE or a DELETE; the
-- reason set is an ARRAY (asking a CHECK for its length first would raise 22023, which is
-- outside the refusal taxonomy); and every atom in that array is an object drawn from the
-- modelled fact families with no key outside the closed union.
--
-- The prefix is TRAPPOINT, not the vertical's name: this is a substrate object rendered
-- into a vertical's schema, and spec/errors.md section 3.2 assigns TRAPPOINT to the kernel
-- templates. A consumer parses that prefix, so it is stable.
--
-- `(NEW).column`, not `NEW.column`. Measured on CockroachDB v26.2.5: the unparenthesised
-- form fails at CREATE TRIGGER with 42P01. Assigning the payload to a local variable first
-- is not stylistic either — a JSONB field of NEW used directly inside a subquery has no
-- data source to bind to.

CREATE FUNCTION trappoint_ref.fn_refusal_ledger_guard() RETURNS TRIGGER
  LANGUAGE plpgsql
  AS $fn$
DECLARE
  v_payload JSONB := NULL;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT: this table is append-only; write a new row';
  END IF;
  v_payload := (NEW).payload;
  IF jsonb_typeof(v_payload->'mus') <> 'array' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT: the reason set is not an array — a refusal with no reason set is not evidence';
  END IF;
  IF jsonb_array_length(v_payload->'mus') = 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT: the reason set is empty — a refusal with no reason set is not evidence';
  END IF;
  IF EXISTS (
       SELECT 1
         FROM jsonb_array_elements(v_payload->'mus') AS a(atom)
        WHERE jsonb_typeof(a.atom) <> 'object'
           OR a.atom->>'kind' IS NULL
           OR a.atom->>'kind' NOT IN ('obligation', 'clause', 'event', 'authority_gap', 'capability_gap'))
  THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT: a reason-set atom names no modelled fact family';
  END IF;
  IF EXISTS (
       SELECT 1
         FROM jsonb_array_elements(v_payload->'mus') AS a(atom),
              jsonb_object_keys(a.atom) AS k(key_name)
        WHERE k.key_name NOT IN ('kind', 'obligation_id', 'origin', 'clause_id', 'event_id', 'severity', 'virulence', 'detail', 'commit_id', 'relation', 'key', 'capability', 'required_value', 'observed_value'))
  THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'TRAPPOINT: a reason-set atom carries a key outside the closed vocabulary';
  END IF;
  RETURN NEW;
END
$fn$;
