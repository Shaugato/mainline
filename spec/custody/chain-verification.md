<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `fn_permit_event_chain` — the normative body

**Normative for `verticals/mainline/db/migrations/0105_fn_permit_event_chain.sql` and its
`cr_event` mirror `0106_fn_cr_event_chain.sql`, welded to the tables declared in `0059` /
`0060` by `0125` / `0126`.** Custody specifies this function; the kernel/datamodel lead
implements it; `scripts/custody/check_chain_fn_matches_spec.py` compares the body below
against the migration source **and** against the live `pg_get_functiondef()` in CI, so this
file and the database cannot drift.

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
DECLARE
  v_existing INT8;
  v_expected BYTES;
BEGIN
  IF (NEW).seq = 0 THEN
    RETURN NEW;
  END IF;

  -- The one aggregate this body is allowed (§4.1 law 4), and the genesis test that survives both
  -- spellings of "first row": ARCHITECTURE §5.11's `seq = 0` and the shipped table's
  -- `seq = 1, prev_seq = 0` under CHECK (seq > prev_seq AND prev_seq >= 0), which makes seq = 0
  -- unreachable. The table is append-only, so this count only rises and the exemption is taken
  -- once per subject; a later row claiming genesis falls through to the predecessor lookup below
  -- and is refused there, with `UNIQUE (permit_id, prev_seq)` as the structural backstop.
  SELECT count(*) INTO v_existing
    FROM mainline.permit_event e0
   WHERE e0.permit_id = (NEW).permit_id;
  IF v_existing = 0 THEN
    RETURN NEW;
  END IF;

  SELECT e.chain_digest INTO v_expected
    FROM mainline.permit_event e
   WHERE e.permit_id = (NEW).permit_id
     AND e.seq = (NEW).prev_seq;

  IF v_expected IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no predecessor event for the declared prev_seq';
  END IF;

  -- IS DISTINCT FROM rather than <>. A NULL on either side makes <> yield NULL, an IF on NULL
  -- does not execute, and the guard would pass silently on exactly the row it exists to catch.
  IF v_expected IS DISTINCT FROM (NEW).prev_digest THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: prev_digest does not match the predecessor chain digest';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER permit_event_chain BEFORE INSERT ON mainline.permit_event
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_permit_event_chain();
```

`cr_event` mirrors this exactly for `change_request`, as `fn_cr_event_chain` /
`cr_event_chain`, substituting `cr_id` for `permit_id`. The mirror is **derived** by
`check_chain_fn_matches_spec.py`, not transcribed here: a second copy is a second thing to
keep in step.

### 2.1 Why the body spells `(NEW).field`, and why this section moved rather than the migration

Read this before proposing that the migration be re-rendered to match an older revision of
this document. **This section was restated on 2026-08-10 to the body the migration ships,
because the body it previously carried cannot run on the platform this product is pinned
to.** The measurement, not a preference, decided the direction.

**MEASURED — `cockroachdb/cockroach:v26.2.5`, 2026-08-10, A/B on one table in one session.**
Two trigger functions differing only in that spelling were created on one table, and each
was then welded. Both `CREATE FUNCTION`s **succeeded**: the parser accepts `NEW.field`, the
function appears in `pg_proc`, and `pg_get_functiondef()` renders it back happily (folded to
`new.v`, with the usual `VOLATILE`/`NOT LEAKPROOF`/`CALLED ON NULL INPUT`/`SECURITY INVOKER`
block the server inserts). The `CREATE TRIGGER` is where they part:

```text
-- body spells NEW.v
CREATE TRIGGER trg_dotted BEFORE INSERT ON t FOR EACH ROW EXECUTE FUNCTION f_dotted();
ERROR: no data source matches prefix: new in this context
SQLSTATE: 42P01
HINT: to access a field of a composite-typed column or variable, surround the
      column/variable name in parentheses: (varName).fieldName
See: https://go.crdb.dev/issue-v/114687/v26.2

-- body spells (NEW).v — byte-identical otherwise
CREATE TRIGGER trg_parens BEFORE INSERT ON t FOR EACH ROW EXECUTE FUNCTION f_parens();
CREATE TRIGGER
```

So the two spellings are not
interchangeable here: one of them produces a function that exists, renders, and **guards
nothing**, because no trigger can ever be attached to it. That is precisely the failure
shape finding **S9** exists to refuse — an artefact that reads like a control and is not
one — arrived at from the other direction.

The consequence for this document is forced and is worth stating plainly, because a spec
that moves toward its implementation is normally a smell:

* the previous §2 body (`NEW.seq`, `NEW.permit_id`, `NEW.prev_digest`, a single `expected`
  variable, `expected <> NEW.prev_digest`) **cannot be made live on v26.2.5 at all**. No
  cluster, no migration, and no reviewer can make assertions `A3` and `A4` of §3 both green
  for it, because `A4` requires a weld the platform refuses to create;
* therefore there was no choice between "move the spec" and "move the migration". Only one
  of the two candidate bodies can exist as a welded trigger on the pinned engine, and it is
  the shipped one;
* the check that found the drift says the same thing in its own failure text, so a reader
  who meets this only through a red build is told the direction there too. See the
  `RECONCILE` constant in `scripts/custody/check_chain_fn_matches_spec.py`.

**What did not change:** the refusal semantics. Both SQLSTATEs are still `P0001`, both
message texts are byte-identical to the previous revision, and both conformance cases in §4
assert the same strings. The spelling moved. The contract did not. If a future engine makes
`NEW.field` weldable, that is not a reason to move this section back — the shipped spelling
is valid on both, and `(NEW).field` is the spelling the hint itself recommends.

### 2.2 Why it is shaped this way

- **Two `SELECT … INTO`, no CTE, no `CASE` expression.** CTEs in triggers are supported from
  v25.1, but this function does not need one, and the narrower the construct the smaller the
  platform surface a migration depends on (`GT-13` records that `digest()` inside a `STORED`
  computed column, `NOT VALID` on `CHECK`, and JSONB `?` immutability inside a `CHECK` are
  each unverified). Nested `IF`/`ELSIF` is the fallback that is known to work.
- **Genesis is detected twice, because "the first row" has two spellings.** ARCHITECTURE
  §5.11 writes the genesis event as `seq = 0`; the shipped table writes it as
  `seq = 1, prev_seq = 0` under `CHECK (seq > prev_seq AND prev_seq >= 0)`, which makes
  `seq = 0` **unreachable** on `mainline.permit_event`. The `(NEW).seq = 0` early return
  therefore holds the architecture's spelling, and the `count(*) = 0` probe holds the
  shipped one. The table is append-only, so the count only rises, and the exemption is taken
  at most once per subject; a later row claiming to be genesis falls through to the
  predecessor lookup and is refused there. `linear UNIQUE (permit_id, prev_seq)` is the
  structural backstop that prevents a second row extending the same head.
- **`IS DISTINCT FROM`, not `<>`.** A `NULL` on either side makes `<>` evaluate to `NULL`,
  an `IF` on `NULL` does not execute its branch, and the guard would pass silently on
  exactly the row it exists to catch. `prev_digest` is `NOT NULL` in the shipped table, so
  today the difference is unobservable — which is the argument for writing the total
  operator now, while the column definition is not what the guard depends on.
- **A missing predecessor and a mismatched digest are different messages.** The diagnosis is
  the deliverable. "An exception was raised" is worthless in a refusal-shaped product, and a
  conformance case asserts the exact message text of each.
- **`P0001`, not `23514`.** This is a `RAISE` from a trigger body, and the SQLSTATE contract
  classes `P0001` as REFUSE: attempted exactly once, recorded, surfaced as a refusal
  payload, never retried.

### 2.3 What it does not do

It does not make `chain_digest` evidentiary. `chain_digest` is a hash over CockroachDB's own
`JSONB` normalisation, and **a third party cannot reproduce CockroachDB's key ordering**.
The evidentiary hash lives in the custody ledger under RFC 8785 JCS.

Both chains exist because **they fail differently**: the server-side chain is refused at
write time by the database and cannot be forged by an application bug; the JCS chain is
verifiable by a stranger and cannot be forged by a rogue DBA. Neither is a substitute for
the other, and the design says so rather than letting a reader assume the stronger one.

---

## 3. The conformance check

`scripts/custody/check_chain_fn_matches_spec.py` extracts the single fenced `sql` block in
§2 above, derives the `cr_event` mirror from it, and runs **four** assertions per variant —
eight lines of output, each of which is a `PASS`, a `FAIL`, or a `SKIP` printed in the same
column and the same voice.

| id | subject | needs a cluster | what it compares |
|---|---|---|---|
| `A1` | spec ↔ migration | no | the §2 `CREATE FUNCTION` against `0105` / `0106` |
| `A2` | spec ↔ weld | no | the §2 `CREATE TRIGGER` shape against `0125` / `0126` |
| `A3` | spec ↔ live | **yes** | the §2 body against the live `pg_get_functiondef()` |
| `A4` | weld ↔ live | **yes** | `pg_get_triggerdef()` — the trigger is still attached |

`A1` and `A2` normalise both sides: comments removed, runs of whitespace collapsed, text
outside string literals and quoted identifiers lowercased, and the dollar-quote delimiter
folded to `$$`. Normalisation stops there deliberately. It does **not** rewrite
`(NEW).seq` to `NEW.seq`, though that too would be meaning-preserving in isolation:
anything more aggressive lets a semantic change pass, and the whole point is that the body
the database is running is the body this document specifies.

### 3.1 `A3` is a probe, and cannot be a text diff

**MEASURED on `cockroachdb/cockroach:v26.2.5`, 2026-08-10.** `pg_get_functiondef()` does not
return the submitted text; it re-prints the parsed tree. The same body submitted verbatim
comes back with comments removed and tab indentation imposed, `NEW` folded to `new`, `<>`
rewritten to `!=`, `SELECT … INTO x FROM t` rewritten as `SELECT … FROM t AS t INTO x` with
the `INTO` clause relocated to the end and table aliases synthesised, `WHERE a AND b`
rewritten as `WHERE (a) AND (b)`, and an attribute block
(`VOLATILE` / `NOT LEAKPROOF` / `CALLED ON NULL INPUT` / `SECURITY INVOKER`) inserted that
the submitted text never contained.

A textual comparison of §2's source against that rendering would therefore report a
difference **when the bodies are identical**, and the only normaliser that could suppress it
would be aggressive enough to hide a real semantic change — the thing the paragraph above
forbids. So `A3` puts *both* sides through the same renderer: the §2 body is created under a
throwaway schema named from `secrets`, the server is asked to render it, the schema is
dropped in a `finally`, and the two renderings are compared. **`A3` therefore writes to the
target cluster.** That is stated here rather than discovered; `--no-probe` turns it off, at
the cost of `A3` reporting `SKIP`, because there is no sound textual substitute.

### 3.2 Exit codes, and what a `SKIP` means

* `0` — every *applicable* assertion held. Skips are possible and are printed loudly,
  each naming what was not checked and why, followed by a summary line
  `NOT CHECKED: the run above skipped N assertion(s)`.
* `1` — an assertion failed, **or** `--strict` was given and anything was skipped. The K2
  exit gate uses `--strict`, so "nobody looked" is a failure there.

A `SKIP` is never a `PASS` and never silent. The three that occur in practice, by name:

| skip | cause | how to clear it |
|---|---|---|
| `A3/A4 live conformance: no cluster` | no `--dsn` and none of `MAINLINE_TEST_DSN` / `COCKROACH_URL` / `CRDB_URL` / `TRAPPOINT_DSN` / `LOCAL_DSN` is set, or `psycopg` is absent | point the check at a node |
| `A3/A4 …: mainline.permit_event does not exist on this cluster` | the node is reachable but the migration chain has not been applied to that database | `trappoint migrate bootstrap`, then `trappoint migrate up --tree mainline --migrations verticals/mainline/db/migrations --attest final`. `--attest final` is not decoration: measured 2026-08-10 on v26.2.5, the default `--attest each` refuses at `0120_trg_check_project` with *"the schema fingerprint is not stable across two consecutive computations"* and leaves that version DIRTY, whose only recovery is a fresh database |
| `A3 …: the server refused the probe schema` | the role cannot `CREATE SCHEMA` — a read-only credential cannot run `A3` | run `A3` as a role that can, or accept the skip and say so |

`.github/workflows/custody-chain.yml`'s `policy-and-spec` job starts a disposable
single-node cluster and applies the chain to it precisely so that none of the three fires
there, and asserts `--strict` so that a regression to any of them is a red build rather than
a quieter green one.

---

## 4. Conformance cases

`seq = 0` is unreachable on the shipped tables — `CHECK (seq > prev_seq AND prev_seq >= 0)`
forces `seq >= 1` — so the genesis row is `seq = 1, prev_seq = 0` and the exemption that
admits it is the `count(*) = 0` probe, not the `(NEW).seq = 0` early return. Both are
specified in §2 and §2.2 explains why; the cases below exercise the reachable one.

| Case | History | Asserts |
|---|---|---|
| `CF-S9a` | insert `seq = 2, prev_seq = 1` with a fabricated `prev_digest` | `P0001`, message `…does not match the predecessor chain digest` |
| `CF-S9b` | insert `seq = 5` naming `prev_seq = 4` when no `seq = 4` row exists | `P0001`, message `…no predecessor event for the declared prev_seq` |
| `CF-S9c` | insert the first event for a subject (`seq = 1, prev_seq = 0`) with any `prev_digest` | admitted (`00000`) — genesis has no predecessor, and `count(*) = 0` is what admits it |
| `CF-S9d` | two concurrent transitions from the same head | one commits, one gets `23505` on `linear` — a chain, not a tree |
| `CF-S9e` | `DROP TRIGGER permit_event_chain`, then repeat `CF-S9a` | the insert **succeeds**, and the custodian patrol raises it as an attested ledger leaf within one cycle (attack **A13**) |
| `CF-S9f` | a *second* row claiming genesis for a subject that already has events | refused — the `count(*) = 0` exemption is spent, so it falls through to the predecessor lookup, and `linear UNIQUE (permit_id, prev_seq)` is the structural backstop |

`CF-S9e` is the honest one. Nothing stops a T1 adversary dropping a trigger. What the design
guarantees is that the drop is **loud** — `A4` in §3 is the CI-side half of that guarantee,
and the unwelding suite asserts refusal depth on the paths where a second mechanism exists.

---

## References

- ARCHITECTURE.md §5.5 (`permit_event` DDL), §5.11 item 8, §19 `GT-13`
- `research/08-synthesis/review-adversarial.md` S9
- `spec/errors.md` (the SQLSTATE contract), [`attacks.yaml`](attacks.yaml) A11, A13
- `docs/leads/custody.md` §2 CU-9
- `scripts/custody/check_chain_fn_matches_spec.py` (the executable half of §2 and §3)
- CockroachDB issue <https://go.crdb.dev/issue-v/114687/v26.2> (§2.1, the forced spelling)
