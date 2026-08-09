-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI28, MI01
-- I: I12, I01
-- COUNSEL-GATED: no
-- RATIONALE: I12 — no elevated control state de-escalates by timeout, and de-escalation requires a positive evidence row. This is the mirror obligation: a lease that is CALLED must leave a row saying what falsified it and when. `mechanism_predicate.state = 'revoked'` is a flag; this table is the evidence behind the flag, append-only, and it is what makes the M8 exhibit — "it called itself at 04:12, before anything happened" — a record rather than a claim.
--
-- migration:  0065b_predicate_revocation
-- band:       0065-0065z · datamodel/ex-dm-gate · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). ARCHITECTURE §3's
--             worker table listed `predicate_revocation` under `dm-periphery`; the allocation
--             file is the authority (MR-6 lock 1) and it grants 0065-0065z here, next to the
--             table it evidences. Where prose and that file disagree, that file is what is true.
-- statements: 1
-- source:     ARCHITECTURE.md §5.5 (M8) · §4.1 I12 · §6 the append-only list · §16 MI28
-- requires:   0065 mainline.mechanism_predicate
-- projects:   nothing. AUTHORITATIVE: the revocation trigger in band 0140-0149z reads this table
--             to move `mechanism_predicate.state` and to re-open the dispositioned checks.
-- sqlstate:   23503 on fk_revocation_predicate; 23514 on falsified_by_stated;
--             23505 on the primary key; P0001 from the append-only trigger
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY THERE IS NO `UNIQUE (predicate_id)`, AND WHY THAT IS A DECISION RATHER THAN AN OMISSION.
--
-- A lease is called once, so a unique constraint here looks obviously right. It is wrong, and the
-- reason is the one this whole product is built on: a second falsification is a FACT, and a
-- schema that refuses to record a fact has chosen to destroy evidence to keep a flag tidy.
--
-- Two register signals can falsify the same predicate within the same second — a hazardous-goods
-- register add and a vessel-class change, arriving from two different feeds. Under a UNIQUE
-- constraint the second is a 23505, the writer swallows it as "already revoked", and the record
-- of the second falsification does not exist anywhere. At an inquiry, "what did the firm know and
-- when" is answered from a set of one, having silently discarded the other. Both rows are
-- therefore admitted, and "which one called the lease" is `min(falsified_at)` — an ordering over
-- recorded facts rather than an accident of which INSERT arrived first.
--
-- The state machine is unaffected: `mechanism_predicate.state` moves 'holding' -> 'revoked' on
-- the FIRST revocation and the trigger that does it is idempotent by construction, because a
-- second move to 'revoked' changes nothing.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- APPEND-ONLY (MI01, I01). Nothing in this table is ever amended. `fn_refuse_mutation` (band
-- 0100-0109z, RENDERED) is the mechanism and the trigger that attaches it to this table belongs
-- to band 0140-0149z; §6's list is the authority for which tables receive it. UNTIL THAT TRIGGER
-- LANDS THIS TABLE IS MUTABLE BY ANY WRITER WITH THE GRANT, and the test suite carries that as a
-- deliberately RED assertion rather than as an assumption.
--
-- `falsified_by` IS A LOCATOR, NOT A NARRATIVE. It names the register row or event that made the
-- predicate false — a `mainline_ops.site_register_signal` id, a register key, an event ref — in a
-- form the router can hand back to a reader who asks "show me the thing that called this". It is
-- STRING and not UUID because the falsifying object is not always one of ours: a site register is
-- the customer's system and its identifiers are the customer's shape. `falsified_by_stated`
-- refuses the empty string, because '' satisfies NOT NULL and prints as an answer.
--
-- `observed_evidence` IS THE FROZEN OBSERVATION and it is JSONB with no CHECK over it, which is
-- deliberate under DM-4: no JSONB operator appears in any CHECK in this schema. Its shape is the
-- router's contract, not the schema's, and the thing that makes it trustworthy is that it is
-- written in the same transaction as the revocation and never afterwards.
--
-- `falsified_at` DEFAULT now() IS THE SERVER CLOCK, and the demo beat depends on that. "It called
-- itself at 04:12, BEFORE whatever happened next" is only an exhibit if the timestamp is the
-- database's and not the caller's. A client-supplied value is accepted where a genuine external
-- observation time is known, which is why there is no CHECK forbidding it — but the default, and
-- what the automatic path writes, is the transaction clock.
--
-- VERIFIED 2026-08-10 against CockroachDB CCL v26.2.5 (local single node, insecure, 26257). The
-- statement applies; TWO revocations of one predicate, from two different falsifying sources,
-- BOTH insert — which is the decision this file's header argues for, now measured rather than
-- intended; and a revocation naming a predicate that does not exist is refused with SQLSTATE
-- 23503 and the server names `fk_revocation_predicate`. Evidence:
-- tests/integration/schema/test_mi_boundary_override.py::
-- test_two_falsifications_of_one_lease_are_both_recorded.

CREATE TABLE mainline.predicate_revocation (
  revocation_id     UUID   NOT NULL DEFAULT gen_random_uuid(),
  predicate_id      UUID   NOT NULL,
  falsified_by      STRING NOT NULL,   -- the register row / event that made it false
  falsified_at      TIMESTAMPTZ NOT NULL DEFAULT now(),   -- SERVER clock; see the header
  observed_evidence JSONB  NOT NULL,
  CONSTRAINT predicate_revocation_pk PRIMARY KEY (revocation_id),
  CONSTRAINT fk_revocation_predicate FOREIGN KEY (predicate_id)
    REFERENCES mainline.mechanism_predicate (predicate_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT falsified_by_stated CHECK (falsified_by <> ''),
  -- "Which revocation called the lease" is min(falsified_at) over this index, not a UNIQUE that
  -- would have refused the second falsification. See the header.
  INDEX by_predicate (predicate_id, falsified_at)
);
