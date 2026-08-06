<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The SQLSTATE contract

**Normative.** Part of TRAPPOINT `1.0.0-rc.1`. Changing any code in §1 or §2, or moving a code
between classes, is a **MAJOR** bump.

A product whose deliverable is a refusal cannot treat error handling as plumbing. The set of codes a
conformant implementation may produce is **closed**, the behaviour of a conformant client on each
code is **fixed**, and any code outside the set is a **defect**, not an edge case — because it means
the database refused for a reason nobody modelled.

---

## 1. The four expectation classes

Every attempted history has exactly one expectation class. The class is recorded per case in
[`conformance/manifest.toml`](conformance/manifest.toml) as `class`.

| Class | Codes | Meaning | Conformant client behaviour |
|---|---|---|---|
| **RETRY** | `40001` | serialization failure; the transaction is *undecided* | retry with capped exponential backoff and full jitter, then surface a refusal |
| **REFUSE** | `23514` `23503` `23505` `P0001` | the gate decided: **no** | attempted **exactly once, ever**; recorded; surfaced as a refusal payload |
| **DENY** | `42501` | the writer never reached the gate — insufficient privilege or an RLS policy | surfaced as an authorisation error; **never** retried; **never** recorded as a gate refusal |
| **ADMIT** | `00000` | the history must complete | asserted positively; used for cases that prove a legal path stays legal |

`00000` is not an error. It appears in the manifest's `expect_sqlstate` field so that every case has
a uniform, machine-checkable expectation, including the cases whose whole point is that a *correct*
history is **not** refused (deduplication absorbing a duplicate, a merge succeeding under forced
row-level security, a history reconstructed from the event chain).

### 1.1 Totality

> Over the gate path, the refusal taxonomy is **total** over `{40001, 23514, 23503, 23505, P0001}`.
> Any other SQLSTATE fails the conformance suite.

"Gate path" means: a transition attempted by a role that already holds the grants and policies needed
to attempt it. `42501` is excluded from the taxonomy not by exception but by definition — the writer
was refused *before* the gate, by the grant graph or by a row-level-security policy, and no gate
condition was ever evaluated. `test_taxonomy_totality` therefore applies to cases whose `class` is
`gate` or `retry`, and cases whose class is `deny` assert `42501` explicitly.

Codes a conformant implementation MUST NOT produce on the gate path, listed because each has a
specific cause worth naming:

| Code | Why it is a defect |
|---|---|
| `23502` | a `NOT NULL` projected column was left unset by a trigger — see spec P-4; project the strictest legal value instead |
| `22P02` / `22003` | a client sent a value the column type cannot hold; the gate never ran |
| `42883` / `42P01` | the schema is not migrated to the version the client expects |
| `40003` / `25P02` | statement completion unknown, or a statement was issued after an aborted one — a client bug in transaction handling |
| `53200` / `57014` | resource exhaustion or cancellation; the transition is undecided but is **not** a serialization failure and MUST NOT be treated as one |
| `XXUUU` | an internal error; report it upstream and do not model it |

---

## 2. The five modelled codes

### 2.1 `40001` — the ONLY retryable code

`40001` (`serialization_failure`, in CockroachDB carrying `TransactionRetryWithProtoRefreshError`)
means the transaction did not happen and the database is inviting the client to try again. It is the
**only** code a conformant client may retry.

Normative client behaviour:

- retry the **whole transaction**, from `BEGIN`, never a statement;
- capped exponential backoff **with full jitter**; a bounded attempt count; and a final surfaced
  refusal when the budget is exhausted;
- the isolation level MUST be set explicitly on every gate transaction
  (`SET TRANSACTION ISOLATION LEVEL SERIALIZABLE`) and never inherited from a pool default;
- retry counters are Class A telemetry (operational), never Class B (evidentiary).

### 2.2 `23514` — `check_violation`

A `CHECK` constraint refused the row. This is the **primary product surface**: the six merge-gate
refusals, the clearance requirement flags, the bounded-window rules and the non-negativity guards all
land here. `diag.constraint_name` carries the exhibit.

### 2.3 `23503` — `foreign_key_violation`

A composite foreign key refused the row. Two shapes matter, and both are deliberate:

- **the clearance lattice** — `(virulence, kind)` referencing the versioned legal-verdict table, so
  a verdict that does not exist for that ancestral severity is not a warning but a missing row;
- **the epoch pin** — `(subject_id, gate_epoch)` under `ON UPDATE RESTRICT`, so mutating the epoch of
  a subject whose transition is already recorded is refused by referential integrity.

### 2.4 `23505` — `unique_violation`

A unique constraint or unique index refused the row: the compare-and-swap on an event chain head, the
one-completion-per-subject primary key, the single-live-disposition partial index, the deduplication
digest. `diag.constraint_name` carries the **index or constraint name**, which is the exhibit.

### 2.5 `P0001` — `raise_exception`

A substrate trigger function, UDF or procedure refused deliberately. `P0001` is reserved for the
conditions no `CHECK` can express:

1. a condition depending on `now()` (expiry, staleness, a bounded window measured at write time);
2. a condition over the **absence** of a row in another relation (a missing authority-source row, a
   missing certificate, a missing person record) — *absence of evidence refuses*;
3. a condition over an **aggregate** of another relation (an anti-join re-derivation);
4. **drift**: a re-derived value disagreeing with the projected value;
5. append-only enforcement, and the single declared exception to it.

`diag.constraint_name` is **empty** for `P0001`. The exhibit is therefore the **fully-qualified name
of the raising object**, which the message MUST make recoverable (§3.2).

---

## 3. The exhibit, and how a client recovers it

### 3.1 `expect_constraint` semantics

Every conformance case carries a non-empty `expect_constraint`. It is the **exhibit name** — the
exact identifier the assertion names — and its meaning depends on the code:

| Code | `expect_constraint` is |
|---|---|
| `23514` `23503` `23505` | the constraint or unique-index name reported in `diag.constraint_name`, verbatim |
| `P0001` | the fully-qualified name of the trigger function, UDF or procedure that raised, e.g. `mainline.fn_permit_merge_gate` |
| `40001` | the projected column that carried the materialised conflict, in `schema.table.column` form |
| `42501` | a structured grant token, `grant:<verb>:<object>:<role>`, naming the privilege whose absence denied the write, or the RLS policy name where a policy denied it |
| `00000` | the name of the SQL object that had to *permit* the write for the history to complete |

A test asserting only a SQLSTATE is **not conformant**. *"An exception was raised"* is worthless in a
product whose deliverable is the diagnosis.

### 3.2 The `P0001` message convention

A `RAISE` from substrate code MUST use `ERRCODE = 'P0001'` and a message of exactly this shape:

```
<PREFIX>: <one sentence, lower case, no trailing full stop>
```

where `<PREFIX>` is:

| Prefix | Used by |
|---|---|
| `TRAPPOINT` | substrate objects: the kernel templates, the migration runner, the diagnosis UDF |
| `MAINLINE` | the MAINLINE vertical's own trigger functions |
| `<VERTICAL>` | any other vertical, upper case, matching `vertical.name` in the binding |

Examples, verbatim from the shipped kernel:

```
MAINLINE: no blame closure for this clause version — cannot arm a check
MAINLINE: precursor arrived after issue — use the post-issue recall path
MAINLINE: merge refused — blame closure not materialised for cited clauses
MAINLINE: this table is append-only; write a new row
TRAPPOINT: projected counter disagrees with the re-derived value — refusing on drift
```

Normative:

- the prefix is **stable**; changing it is a MAJOR bump because clients parse it;
- the sentence after the prefix is **PATCH-mutable**; no client may depend on its wording;
- a message MUST NOT contain a value derived from an untrusted document, because a message is
  rendered in a console and written to a ledger;
- a message MUST NOT name a human's competence, honesty, attentiveness or intent
  (see [`invariants/I15-allegation-firewall.md`](invariants/I15-allegation-firewall.md)); it names
  facts, rows and rules.

Because `diag.constraint_name` is empty for `P0001`, a conformant client recovers the exhibit from
the raising object. Where the driver cannot supply it, the client MAY parse the message prefix and
MUST log that the diagnosis is **weakened**, so a run whose exhibits were inferred is never
indistinguishable from a run whose exhibits were reported.

### 3.3 The synthetic-code ban

> **A synthetic SQLSTATE raised by a trigger MUST NOT impersonate a constraint-backed code.**

Substrate procedural code MUST NOT `RAISE` with `23514`, `23503`, `23505` or `40001`.

- A synthetic `23514`/`23503`/`23505` carries **no constraint name**, so it produces an exhibit
  nobody can name — the exact failure this specification exists to prevent.
- A synthetic `40001` is indistinguishable from a real serialization failure, so a conformant client
  would retry a deterministic refusal until its budget ran out. That is not a bug in the client; it
  is a bug in the raise.

**Corollary.** Where a condition is *also* expressible as a `CHECK` over a projected scalar,
procedural code MUST NOT pre-empt it. The trigger re-derives and raises `P0001` only on drift or on a
condition no `CHECK` can hold; the `CHECK` produces the refusal, with its name. This is why the
merge-gate trigger does **not** raise for a non-zero obligation counter: the counter's own `CHECK`
does, and *"refused by `gate_closed_when_issued`"* is the sentence that matters.

**Corollary 2.** Where a projection trigger's lookup into a typed-verdict table misses, it MUST NOT
raise `23503`. It projects the **strictest** legal values and returns the row, so that the real
composite foreign key fires with its name attached.

---

## 4. Attempt-once, and why it is a property of the product

A refusal is **attempted exactly once, ever**. Not once per retry budget; once.

The reason is evidentiary rather than performance-related. The refusal ledger is a record of
*decisions the gate made*. If a client retries a `23514`, the ledger holds five identical refusals for
one attempted history, and the count of refusals stops being a count of anything. Worse, an
opposing expert reading the ledger sees a system that repeatedly attempted a write the database
had already refused, which is an unhelpful sentence to explain.

**Enforced, not documented:** a conformant repository declares `tenacity`, `backoff` and `retrying`
as **forbidden imports repository-wide** under an import-linter contract, and its retry loop is
hand-written and readable in one screen. A retry spy asserts the once-only property directly:
`40001` retried with capped backoff; the four refusal codes attempted exactly once, ever.

---

## 5. Mapping to the refusal payload

Every REFUSE-class outcome surfaced to a client is emitted as a refusal payload validating against
[`wire/refusal.schema.json`](wire/refusal.schema.json), carrying at minimum `sqlstate`, `constraint`,
the subject identity, the `gate_epoch` at refusal time, the minimal unsatisfiable subset, and the
nearest admissible alternative or an explicit `null` with a reason.

RETRY-class outcomes are **not** payloads: an undecided transaction has no reason set. A retry budget
exhausted without a decision is surfaced as a distinct condition and MUST NOT be represented as a
refusal, because it is not one.

DENY-class outcomes are **not** payloads either. `42501` says the writer lacked authority, which is a
fact about the writer, not a diagnosis of the subject — and emitting a reason set for it would leak
the shape of rows the writer is not entitled to read.
