<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `trappoint-core`

The gate client. One explicit `SERIALIZABLE` transaction, one `CALL`, and a retry loop
that **retries `40001` and nothing else** — because the difference between an undecided
transaction and a decided refusal is the product.

Every `uv run` below is scoped with `--package`. A bare `uv run` builds every workspace
member, so an unrelated distribution mid-edit three directories away would break a
command that has nothing to do with it.

```sh
uv run --package trappoint-core pytest packages/trappoint-core/tests -q
```

The whole suite runs **without a database**. What is asserted here is the client's
contract, and a contract that could only be checked with a container running is a
contract that stops being checked.

---

## 1. The property, in one sentence

> A refusal is **attempted exactly once, ever.** Not once per retry budget; once.

`spec/errors.md` §4. The reason is evidentiary rather than about latency. The refusal
ledger is a record of *decisions the gate made*. If a client retries a `23514`, the
ledger holds five identical refusals for one attempted history and the count of refusals
stops being a count of anything — and an opposing expert reading it sees a system that
repeatedly attempted a write the database had already refused, which is an unhelpful
sentence to have to explain.

`RecordingObserver` asserts it directly rather than letting a green test imply it:

```python
spy = RecordingObserver()
try:
    execute_gate(pool, request, observer=spy)
except GateRefused as refused:
    assert spy.attempts == [0]  # one attempt
    assert spy.attempts_for(refused.sqlstate) == 1  # ever
```

---

## 2. Why there is no `tenacity` here

`tenacity`, `backoff`, `retrying` and `stamina` are forbidden imports **repository-wide**
under `.importlinter` contract 4, and this distribution is the reason the contract
exists. A decorator that retries "on exception" cannot tell an undecided transaction
from a decided refusal. Making the policy a decorator argument also puts it somewhere
nobody reads.

What replaces it is forty lines in `retry.py` with five branches:

| SQLSTATE | Class | What happens |
|---|---|---|
| `40001` | RETRY | capped exponential backoff, **full jitter**, bounded attempts, then `RetryBudgetExhausted` |
| `23514` `23503` `23505` `P0001` | REFUSE | `GateRefused` carrying the exhibit, **on the first attempt, always** |
| `42501` | DENY | `AuthorisationDenied` — the writer never reached the gate |
| anything else | — | `UnmodelledRefusal` — the database refused for a reason nobody modelled |

`RetryBudgetExhausted` is deliberately **not** a `GateRefused`. A budget spent without a
decision is not a refusal; the gate never got to say anything.

Full jitter rather than equal jitter because the failure being defended against is N gate
workers colliding on one hot subject and then retrying in lockstep — equal jitter keeps a
synchronised herd synchronised through its first retry.

---

## 3. The exhibit, and a platform measurement that changed the design

A test that asserts "an exception was raised" is worthless in a product whose deliverable
is the diagnosis, so every `GateRefused` carries a `constraint`. For `23514`/`23503`/
`23505` that is `diag.constraint_name`. For `P0001` the specification says it is the
fully-qualified name of the raising object.

**Measured on CockroachDB CCL v26.2.5 through psycopg 3.3.4**, a PL/pgSQL `RAISE`
arrives with:

* `diag.constraint_name` → `None` — expected, `spec/errors.md` §3.1 says so;
* `diag.context` → `None` — **not** expected; PostgreSQL populates a PL/pgSQL context
  stack naming the function and line, and CockroachDB does not;
* `diag.source_function` → `'func397'`, a CockroachDB Go internal, which names nothing.

So on this platform the driver cannot supply the raising object, and `spec/errors.md`
§2.5's requirement that *the message* make it recoverable is the only channel left. The
kernel's SQL templates therefore emit every refusal as

```
<PREFIX>: merge refused by <schema>.<object> — <what and why>
```

and `diagnose()` reads the object out of it with a regex that admits exactly one shape: a
lower-case, dot-qualified SQL identifier. Free text cannot become an exhibit — an exhibit
is written to a ledger and read in a courtroom.

Three tiers, and the tier is reported:

| Tier | Source | `weakened` |
|---|---|---|
| 1 | `diag.constraint_name` | `False` |
| 2 | the `refused by <object>` clause the substrate emits | `False` |
| 3 | the message prefix alone | **`True`**, and logged at `WARNING` |

A run whose exhibits were inferred must never be indistinguishable from a run whose
exhibits were reported.

---

## 4. `execute_gate`

```python
from psycopg_pool import ConnectionPool
from trappoint_core import MergeRequest, execute_gate, leaf_hash

canon = jcs.canonicalise(payload)  # trappoint-jcs, RFC 8785
execute_gate(
    pool,
    MergeRequest(
        schema="mainline",
        subject_kind="permit",
        subject_id=permit_id,
        merged_commit=commit_id,  # 32 bytes
        merged_by=actor_sub,
        actor_kind="human",
        payload=payload_json,
        canon_bytes=canon,
        payload_ver=1,
        leaf_hash=leaf_hash(canon),  # SHA-256(0x00 || canon)
        gate_epoch=observed_epoch,
    ),
)
```

Three things about that call are normative, not stylistic.

**The isolation level is asserted, never inherited.** `SET TRANSACTION ISOLATION LEVEL
SERIALIZABLE` is the first statement of every attempt (`spec/errors.md` §2.1). A pool
default is a setting somebody can change in a deploy without touching a line of code, and
the gate's correctness argument rests entirely on the level actually in force. Issuing
the statement puts it in the wire log where an auditor can see it.

**The retry unit is the whole transaction.** A `40001` retry re-enters from `BEGIN` on a
fresh connection. Replaying a statement into an aborted transaction produces `25P02`,
which the taxonomy names as a client bug in transaction handling.

**The evidentiary hashes are supplied, the derivable facts are not.** `canon_bytes` and
`leaf_hash` come from the client because SQL cannot canonicalise to RFC 8785 — CockroachDB's
JSONB key ordering is not reproducible by a third party, so a server-computed leaf would
be a hash nobody outside the cluster could check. Everything a client could *lie* about
and a reader could *verify* — `clearance_digest`, `prev_digest`, `site_code`, the observed
obligation count — is computed by the procedure from the base tables.

`execute_gate` returns `None`. A merge that returns is a merge that committed; there is
deliberately no truthy result to mistake for one.

---

## 5. `cas` — the gap-free ledger append

```
seq := coalesce(max(seq) + 1, 0)      -- derived INSIDE the caller's transaction
PRIMARY KEY (site_code, seq)          -- the compare-and-swap
UNIQUE (site_code, prev_link_hash)    -- and the fork check
```

Two appenders that read the same `max(seq)` both try to write the same position and one
gets `23505`. Nothing is allocated, nothing is cached, nothing is handed out ahead of a
commit — **so a gap MEANS tampering.** That sentence is the entire evidentiary value of
the structure, and it is false the moment a sequence exists: a sequence gap can be a
crash, a rollback, a cache loss or a deletion, and a log that cannot distinguish those
four asserts nothing about any of them.

`CREATE SEQUENCE`, `nextval(`, `SERIAL` and `unique_rowid()` are banned by `trappoint
render` and `trappoint migrate lint` (ruling D10), and that lint is **load-bearing rather
than decorative**: ground-truth finding F4 measured that `CREATE SEQUENCE` succeeds on
this cluster. `assert_gap_free()` applies the same test to a string of SQL, and it is
careful about a trap worth naming — a substring test for `SERIAL` refuses `SET
TRANSACTION ISOLATION LEVEL SERIALIZABLE`, which is the one statement every gate
transaction must issue.

`assert_dense()` is the audit-side check: `count(*)` must equal `max(seq) + 1`. It is
O(partition) and is **not** on the append path; it belongs to the verifier, the nightly
fixity patrol and the conformance suite.

Two append paths with identical semantics: `append_leaf()` derives in Python (the link
arithmetic is then unit-testable without a cluster) and `append_leaf_server_side()` calls
migration `0119`'s `fn_ledger_cas_append()` in one round trip. Neither commits — the
ledger row belongs to whatever transaction produced the fact it records (`INV-3`).

---

## 6. What this package deliberately does not do

* **It does not explain a refusal.** The minimal unsatisfiable subset and the nearest
  admissible alternative are `trappoint-diagnose`'s, computed with the database as the
  oracle so the explanation cannot disagree with the refusal. `GateRefused.as_dict()`
  emits the fields it can prove and leaves those two absent rather than guessing.
* **It does not write the refusal ledger.** Recording is the caller's, and
  `refusals_of()` yields a payload only for a REFUSE-class outcome — `40001` and `42501`
  yield nothing, because an undecided transaction has no reason set and a denial is a
  fact about the writer.
* **It does not know what a permit is.** The schema and the subject kind come from the
  binding. `SUBJECT_KINDS` is the one place the substrate names the two kinds TRAPPOINT
  gates, and adding a third means adding a `[[subject]]` to a binding and a name here in
  the same MINOR.
