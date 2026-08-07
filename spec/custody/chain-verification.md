<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `fn_permit_event_chain` — the normative body

**Normative for `verticals/mainline/db/migrations/0059–0060`.** Custody specifies this
function; the datamodel lead implements it; `scripts/custody/check_chain_fn_matches_spec.py`
diffs the live `pg_get_functiondef()` against the body below in CI, so this file and the
database cannot drift.

Closes adversarial-review finding **S9** and refuses attack **A11**.

---

## 1. The defect this refuses

`mainline.permit_event` carries a server-computed chain:

```sql
prev_digest  BYTES NOT NULL,
chain_digest BYTES AS (digest(prev_digest || payload::STRING::BYTES, 'sha256')) STORED,
-- "server-computed chain: the inserter cannot lie about it"
```

The *digest* is computed server-side. Its **input is not**. `prev_digest` was a plain
client-supplied column with no constraint tying it to the prior row's `chain_digest`, so an
inserter wrote any `prev_digest` it liked and the chain was whatever it said.

The comment claimed a property the schema did not have. That is worse than claiming
nothing, because the comment is **discoverable**, and *"a hash chain inside a table the
adversary owns is a checksum, not evidence"* is exactly the sentence a competent opposing
expert is looking for a place to deploy. Do not ship the sentence unfixed; either verify the
input or delete the comment.

We verify the input.

---

## 2. The normative body

```sql
-- ⟨S9⟩ The permit-event chain is verified, not trusted.
CREATE FUNCTION mainline.fn_permit_event_chain() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE expected BYTES;
BEGIN
  IF NEW.seq = 0 THEN RETURN NEW; END IF;
  SELECT chain_digest INTO expected FROM mainline.permit_event
   WHERE permit_id = NEW.permit_id AND seq = NEW.prev_seq;
  IF expected IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no predecessor event for the declared prev_seq';
  END IF;
  IF expected <> NEW.prev_digest THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: prev_digest does not match the predecessor chain digest';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER permit_event_chain BEFORE INSERT ON mainline.permit_event
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_permit_event_chain();
```

`cr_event` mirrors this exactly for `change_request`, as `fn_cr_event_chain` /
`cr_event_chain`, substituting `cr_id` for `permit_id`.

### 2.1 Why it is shaped this way

- **One `SELECT … INTO`, no CTE, no `CASE` expression.** CTEs in triggers are supported from
  v25.1, but this function does not need one, and the narrower the construct the smaller the
  platform surface a migration depends on (`GT-13` records that `digest()` inside a `STORED`
  computed column, `NOT VALID` on `CHECK`, and JSONB `?` immutability inside a `CHECK` are
  each unverified). Nested `IF`/`ELSIF` is the fallback that is known to work.
- **`seq = 0` returns early**, because the genesis event has no predecessor. Its
  `prev_digest` is unconstrained by this trigger and MUST be 32 zero bytes by column
  default; the `linear UNIQUE (permit_id, prev_seq)` constraint prevents a second genesis.
- **A missing predecessor and a mismatched digest are different messages.** The diagnosis is
  the deliverable. "An exception was raised" is worthless in a refusal-shaped product, and a
  conformance case asserts the exact message text of each.
- **`P0001`, not `23514`.** This is a `RAISE` from a trigger body, and the SQLSTATE contract
  classes `P0001` as REFUSE: attempted exactly once, recorded, surfaced as a refusal
  payload, never retried.

### 2.2 What it does not do

It does not make `chain_digest` evidentiary. `chain_digest` is a hash over CockroachDB's own
`JSONB` normalisation, and **a third party cannot reproduce CockroachDB's key ordering**.
The evidentiary hash lives in the custody ledger under RFC 8785 JCS.

Both chains exist because **they fail differently**: the server-side chain is refused at
write time by the database and cannot be forged by an application bug; the JCS chain is
verifiable by a stranger and cannot be forged by a rogue DBA. Neither is a substitute for
the other, and the design says so rather than letting a reader assume the stronger one.

---

## 3. The conformance check

`scripts/custody/check_chain_fn_matches_spec.py`:

1. extracts the fenced `sql` block above from this file;
2. connects to the target cluster and reads
   `pg_get_functiondef('mainline.fn_permit_event_chain'::regproc)`;
3. normalises both (collapse runs of whitespace, strip comments, lowercase keywords) and
   compares;
4. exits non-zero on a difference, printing a unified diff;
5. exits **0 with `SKIP(no-cluster)` printed loudly** when no cluster is reachable — never
   silently.

Normalisation is deliberately limited to whitespace, comments and keyword case. Anything
more aggressive would let a semantic change pass, and the whole point is that the body the
database is running is the body this document specifies.

---

## 4. Conformance cases

| Case | History | Asserts |
|---|---|---|
| `CF-S9a` | insert `seq = 1` with a fabricated `prev_digest` | `P0001`, message `…does not match the predecessor chain digest` |
| `CF-S9b` | insert `seq = 5` naming `prev_seq = 4` when no `seq = 4` row exists | `P0001`, message `…no predecessor event for the declared prev_seq` |
| `CF-S9c` | insert `seq = 0` with any `prev_digest` | admitted (`00000`) — genesis has no predecessor |
| `CF-S9d` | two concurrent transitions from the same head | one commits, one gets `23505` on `linear` — a chain, not a tree |
| `CF-S9e` | `DROP TRIGGER permit_event_chain`, then repeat `CF-S9a` | the insert **succeeds**, and the custodian patrol raises it as an attested ledger leaf within one cycle (attack **A13**) |

`CF-S9e` is the honest one. Nothing stops a T1 adversary dropping a trigger. What the design
guarantees is that the drop is **loud** — and the unwelding suite asserts refusal depth on
the paths where a second mechanism exists.

---

## References

- ARCHITECTURE.md §5.5 (`permit_event` DDL), §5.11 item 8, §19 `GT-13`
- `research/08-synthesis/review-adversarial.md` S9
- `spec/errors.md` (the SQLSTATE contract), [`attacks.yaml`](attacks.yaml) A11, A13
- `docs/leads/custody.md` §2 CU-9
