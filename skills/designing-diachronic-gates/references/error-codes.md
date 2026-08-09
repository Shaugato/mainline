<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# The refusal taxonomy, and how a client recovers the exhibit

A system whose deliverable is a refusal cannot treat error handling as plumbing. Fix a
**closed** set of codes the gate may produce and fix the client behaviour for each. A code
outside the set is a defect, not an edge case: it means the database refused for a reason
nobody modelled.

---

## 1 · The four expectation classes

| Class | Codes | Meaning | Client behaviour |
|---|---|---|---|
| **RETRY** | `40001` | serialization failure; the transaction is *undecided* | retry the whole transaction with capped backoff and full jitter, then surface a refusal |
| **REFUSE** | `23514` `23503` `23505` `P0001` | the gate decided: **no** | attempted **exactly once, ever**; recorded; surfaced with its exhibit |
| **DENY** | `42501` | the writer never reached the gate — privilege or row-level security | surfaced as authorisation; never retried; never recorded as a refusal |
| **ADMIT** | `00000` | the history must complete | asserted positively, so that a legal path staying legal is also a test |

`00000` belongs in the table. Half of a gate suite should be histories whose whole point is
that a **correct** history is not refused; a gate that refuses everything passes any suite
that only tests refusals.

Codes that must not appear on the gate path, each with a specific cause worth naming:

| Code | What it actually means |
|---|---|
| `23502` | a `NOT NULL` projected column was left unset by a trigger — project the strictest legal value instead |
| `22P02` / `22003` | a client sent a value the column type cannot hold; the gate never ran |
| `42883` / `42P01` | the schema is not migrated to the version the client expects |
| `40003` / `25P02` | statement completion unknown, or a statement issued after an aborted one — a client bug in transaction handling |
| `53200` / `57014` | resource exhaustion or cancellation; the transition is undecided but is **not** a serialization failure and must not be retried as one |

---

## 2 · What the exhibit is, per code

The **exhibit** is the identifier a test asserts and a reader is shown. A test asserting
only a SQLSTATE is not an assertion — a typo in a column name produces `23514` too.

| Code | Exhibit | Where it comes from |
|---|---|---|
| `23514` | the constraint name, verbatim | the `CONSTRAINT:` line / `diag.constraint_name` |
| `23503` | the foreign-key constraint name | same |
| `23505` | the unique constraint or index name | same |
| `P0001` | the fully-qualified name of the raising object | **the message** — the server sends no constraint |
| `40001` | not a refusal; record the projected column that carried the materialised conflict | — |
| `42501` | the privilege or the policy that denied the write | the grant graph, not the error |

Observed on v26.2.5, `cockroach sql` printing a `CHECK` violation:

```
ERROR: failed to satisfy CHECK constraint ((state != 'closed':::STRING) OR (open_blocking = 0:::INT8))
SQLSTATE: 23514
CONSTRAINT: gate_closed_when_issued
```

and a `P0001`, which has **no** `CONSTRAINT:` line at all:

```
ERROR: GATE: refused by fn_subject_close_gate — re-derived open obligation count is 1 while the projected counter reads zero
SQLSTATE: P0001
```

---

## 3 · The `P0001` message convention

Because the driver supplies nothing, the exhibit has to be recoverable from the message. Fix
one shape and use it everywhere:

```
<PREFIX>: refused by <schema>.<object> — <one sentence, lower case, no trailing full stop>
```

* the prefix is **stable** — clients parse it, so changing it is a breaking change;
* the sentence after it is free to change — no client may depend on its wording;
* a client that recovered the exhibit by parsing must record the diagnosis as **weakened**,
  so a run whose exhibits were inferred is never indistinguishable from a run whose exhibits
  the server reported. `assert_gate_refuses.py` prints `(parsed)` for exactly this;
* the message must not contain a value taken from an untrusted document — it is rendered in
  consoles and written to logs;
* the message names facts, rows and rules. It never names a person's competence, honesty,
  attentiveness or intent. A refusal is a statement about a state, and a system that editorialises
  about people in its error strings will have those strings read aloud somewhere unpleasant.

---

## 4 · The synthetic-code ban

> **Procedural code must not `RAISE` with `23514`, `23503`, `23505` or `40001`.**

* A synthetic `23514`/`23503`/`23505` carries no constraint name, so it produces an exhibit
  nobody can name — the exact failure the design exists to prevent.
* A synthetic `40001` is indistinguishable from a real serialization failure, so a
  *correct* client will retry a deterministic refusal until its budget runs out. That is not
  a client bug; it is a bug in the raise.

**Corollary.** Where a condition is *also* expressible as a `CHECK` over a projected scalar,
the trigger must not pre-empt it. The trigger raises only on drift or on a condition no
`CHECK` can hold; the `CHECK` produces the refusal, with its name attached.

**Corollary 2.** Where a projection's lookup into a typed authority table misses, it must
not raise a synthetic `23503`. Project the **strictest** legal value and let the real
foreign key fire with its own name.

---

## 5 · `40001` is the only retryable code, and a refusal is attempted once

Retry the **whole transaction**, from `BEGIN`, never a statement. Capped exponential backoff
with full jitter, a bounded attempt count, and a surfaced refusal when the budget is
exhausted. Set the isolation level explicitly on every gate transaction rather than
inheriting a pool default.

A refusal is attempted **exactly once, ever** — not once per retry budget. The reason is
evidentiary rather than performance-related: if a client retries a `23514`, the refusal log
holds five identical refusals for one attempted history and the count of refusals stops
being a count of anything. It also reads badly in review — a system that repeatedly
attempted a write the database had already refused is an unhelpful thing to explain.

Enforce it rather than documenting it: ban `tenacity`, `backoff` and `retrying` as imports,
keep the retry loop hand-written and readable in one screen, and put a spy in the test suite
that asserts `40001` was retried and the four REFUSE codes were attempted once.

---

## 6 · A refusal payload

Whatever a client surfaces should carry at minimum: `sqlstate`, the exhibit, whether the
exhibit was `reported` or `parsed`, the subject identity, the epoch at refusal time, the
minimal set of facts that caused it, and the nearest admissible alternative **or an explicit
null with a reason**.

`40001` outcomes are not payloads: an undecided transaction has no reason set, and a budget
exhausted without a decision must not be represented as a refusal, because it is not one.
`42501` outcomes are not payloads either — that is a fact about the writer, not a diagnosis
of the subject, and emitting a reason set for it leaks the shape of rows the writer is not
entitled to read.
