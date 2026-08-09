<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# trappoint-diagnose — QUICKREFUSE

**The minimal unsatisfiable subset and the nearest admissible alternative of a gate
refusal, computed with the database's own constraint engine as the oracle.**

Invariant [`I14`](../../spec/invariants/I14-minimal-refusal.md): *every refusal emits an
irreducible reason set and, where computable, the nearest admissible alternative.*

A gate that only says "no" gets routed around, and an invariant that is routed around is
not an invariant. This distribution is the answer to the most reasonable objection anyone
raises to a system whose product is a refusal — *how am I supposed to know what to do
about it?*

---

## The claim, and what is novel about it

Extracting a minimal unsatisfiable subset is a solved problem **with a SAT or SMT solver**.
The part with no prior art I could find is using an **RDBMS's own constraint engine** as
the oracle:

```sql
SAVEPOINT p;
  -- apply a candidate subset of the facts
  -- attempt the same transition that was refused
ROLLBACK TO SAVEPOINT p;
```

Because the thing answering *"is this admissible?"* is the same engine that produced the
refusal, reading the same rows under the same isolation, **the explanation cannot disagree
with the refusal**. A solver-based answer is a claim about a model of the constraints; this
is a claim about the constraints.

**What is not claimed.** That the alternative is advice worth taking — it is the smallest
change that restores admissibility, which is often not the right thing to do. That the
reason set is *the cause* — it is the irreducible set of modelled facts whose joint
presence produced the refusal. And that a refusal can never be routed around — a
determined organisation can open a different subject, or not use the system at all. The
claim is that the refusal is **explained**, which removes the commonest and most
reasonable motive for routing around it.

---

## Two algorithms, in this order

### 1. Declarative decomposition — primary, deterministic, no probe

The refused constraint maps to the projected counter behind it, and that counter's
**witness rows are the minimal unsatisfiable subset**. For a single-counter refusal there
is no smaller set, because removing any witness leaves the counter non-zero.

| Refused constraint | Counter | Reason set | Alternative |
|---|---|---|---|
| `gate_closed_when_issued` | `open_blocking` | the open `blocking_check` rows | `dispose_obligations` over exactly those |
| `identity_conserved_when_issued` | `open_residue` | the counter, named with its source | `supply_evidence` |
| `conflicts_resolved_when_issued` | `open_conflicts` | the counter | `supply_evidence` |
| `no_open_warrant_when_issued` | `open_warrants` | the counter | `supply_evidence` |
| `boundary_certified_when_issued` | `unmodelled_asset_count` | the counter | `supply_evidence` |
| `reading_floor_when_issued` | `unmet_floor_count` / `countersigned_count` | **both** — remove either and it passes | `supply_evidence` naming the companion |
| `fk_clearance` | the projected `(virulence, kind)` | the missing lattice cell **plus** the obligations that classified it | `substitute_kind` listing the kinds that DO exist, or `null` + `no_legal_verdict_exists` |
| `epoch_pin_*` | `gate_epoch` | the pinned epoch against the attempted one | `fork_subject`, or `supply_evidence` |

It runs **in the database** as `trappoint.explain_refusal(subject_kind, subject_id,
constraint_name[, attempt])` — migration `0119a`, rendered from the binding — so it is one
round trip, one plan, and `EXPLAIN`-assertable in CI. `decompose.py` is the same algorithm
in pure Python: no database needed, which is what lets the minimality property be asserted
before any schema exists.

### 2. QuickXplain over savepoint probes — the general algorithm

Junker's divide-and-conquer conflict extraction, for a composite refusal the decomposition
does not cover, with the savepoint loop above as the oracle. `O(k · log(n/k))` oracle calls
for a conflict of size `k` out of `n` candidates.

### 3. Honest incompleteness — a first-class outcome

`diagnosis: "none"`, `naa: null`, and a reason from a closed set
(`probe_budget_exhausted`, `no_legal_verdict_exists`, `requires_human_authority`,
`not_computable`). Shipping a superset labelled `"declarative"` would be the one failure
mode `I14` exists to prevent, and it is worse than shipping nothing because it looks like
an answer.

`no_legal_verdict_exists` is not a diagnoser failure. It is the product working: *at this
ancestral severity there is no way to sign this away.*

---

## Six safety rules, enforced rather than documented

1. **The probe transaction is SEPARATE from the gate transaction.** `SavepointOracle`
   refuses at construction a connection that is already inside one. Row locks are
   **preserved** across `ROLLBACK TO SAVEPOINT` in CockroachDB (unlike PostgreSQL), so a
   probe sharing the gate's connection would leave the gate holding locks it never took.
2. **Rolled back unconditionally, in a `finally`.** `probe_transaction()` rolls back and
   closes whatever happened inside it — the oracle raising, the plan raising, the caller
   raising. Asserted directly in `tests/test_probe_safety.py`.
3. **Bounded budget** (default 32), reported in `probe_calls`. Past the cap the emitter
   degrades rather than blocking.
4. **Never on the completion path.** Structurally: rule 1 makes sharing the gate's
   transaction impossible.
5. **A statement timeout** on the probe session, so a probe cannot hold locks while a human
   reads a screen.
6. **An unmodelled error is not an answer.** Anything outside the REFUSE-class codes raises
   rather than reporting "inadmissible"; a `42501` reported as a refusal would produce a
   minimal unsatisfiable subset of a permissions problem.

And one rule about what the diagnoser will not invent: **if a projected counter is
non-zero and no witness row resolves behind it, that is DRIFT and the UDF raises `P0001`**
rather than emitting a plausible reason set. The whole value of a diagnosis produced by the
constraint engine is lost the moment the diagnoser is willing to guess.

---

## The allegation firewall (`I15`), in three layers

No substrate artefact may carry a threshold, score or flag characterising a **named
human's** conduct. `signer_sub` may appear as a fact — *who signed* — never as a measure.

* **The types.** The five atom dataclasses are closed. There is no field where a score
  about a person could be placed, so one cannot be constructed.
* **The wire schema.** `additionalProperties: false` on every atom. An unknown key is
  where such a score would arrive, and it is refused.
* **The table.** `refusal_ledger` carries `refusal_no_person_metric`, a plain-column
  `CHECK`, and `fn_refusal_ledger_guard` refuses any atom key outside the closed
  vocabulary — for every writer, including one that never read the schema.

---

## What it ships

| Artefact | What it is |
|---|---|
| `decompose.py` | the declarative decomposition, pure |
| `quickxplain.py` | Junker's algorithm over an `Oracle` protocol, pure |
| `oracle.py` | `SavepointOracle`, `ProbePlan`, `probe_transaction()` |
| `udf.py` | the one-round-trip client for `trappoint.explain_refusal()` |
| `diagnose.py` | `Diagnoser.explain()` — declarative, then probe, then honest |
| `wire.py` / `schema.py` | payload assembly and validation against the shipped schema |
| `ledger.py` | the one INSERT into the append-only refusal ledger |
| `cli.py` | `trappoint-diagnose explain` |
| `0071c` / `0071d` | `refusal_ledger` and its index |
| `0119a` / `0119b` / `0133` | the UDF, the guard function, the append-only trigger |

Migrations are **rendered** from `packages/trappoint-sql/templates/0071c_refusal_ledger.sql.j2`
and `0119a_fn_explain_refusal.sql.j2`, for both bindings. A change to one of those files is
a change to its template followed by a re-render of MAINLINE **and** the reference vertical.

---

## Using it

```python
from trappoint_diagnose import Diagnoser, UdfSource, context_from_exception, load_gate_binding

binding = load_gate_binding("verticals/mainline/vertical.toml")
diagnoser = Diagnoser(binding)

try:
    merge_permit(...)
except GateRefused as refused:  # or a raw driver error, or a replayed ledger row
    context = context_from_exception(
        refused, subject_kind="permit", subject_id=str(permit_id), gate_epoch=epoch
    )
    payload = diagnoser.explain(context, source=UdfSource(connect))
    record_refusal(conn, payload, schema="mainline", recorded_by="mainline-gate-svc")
```

`context_from_exception` is **structural**: it accepts `trappoint_core.GateRefused`, a
`psycopg` error, or anything else carrying a SQLSTATE and a constraint. This distribution
deliberately does not import `trappoint-core`, so a conformance runner, a replay harness
and a fork can all use it.

Offline (no database, for tests and replay):

```python
payload = diagnoser.explain(
    context,
    witnesses=Witnesses(
        counter_values={"open_blocking": 1},
        open_obligations=[OpenObligation(obligation_id=check_id, virulence="blood_fatal")],
        legal_kinds=("applied", "mitigated", "escalated", "emergency_override"),
    ),
)
```

---

## Dependencies: none, and it is a contract

`dependencies = []`. Not a preference — this package decides what a refusal *means*, its
output is written to an append-only ledger and read by an opposing expert, and every
dependency here is another package that expert must trust. There is no `jsonschema` (the
wire schema uses eighteen keywords; `schema.py` implements them and **refuses** an unknown
one rather than validating vacuously), no driver on the import path (the `pg` extra, and
only `oracle.py` / `udf.py` / `ledger.py` touch a connection), and no `tenacity` /
`backoff` / `retrying` — a refusal is attempted exactly once, ever.
`tests/test_packaging.py` asserts all of it.

---

## Running the tests

```
pytest packages/trappoint-diagnose/tests            # 126 cases, no database
TRAPPOINT_DSN=... pytest packages/trappoint-diagnose/tests   # + 17 against a real cluster
```

The one that matters is `test_minimality_oracle.py`: **1000 synthetic constraint systems**,
each one asserting that the returned set is refused, that removing any single element makes
it admissible, and that it is exactly an inclusion-minimal conflict core. `is_minimal_conflict`
is deliberately not implemented in terms of QuickXplain — a test that checked an algorithm
against itself would assert nothing.

The cluster-dependent cases skip with a stated reason when `TRAPPOINT_DSN` is unset. A test
that passes by absence is worse than one that is missing.

---

## Measured on the target platform

CockroachDB **v26.2.5**, local node, 2026-08-09. Every one of these is a measurement:

* `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` after a `23514` returns the transaction to a usable
  state; nested savepoints work. **The probe loop is legal.**
* CTEs inside a PL/pgSQL UDF, `jsonb_strip_nulls`, `jsonb_agg(... ORDER BY ...)`,
  `jsonb_object_keys`, `to_jsonb` over an array, a DEFAULT-valued UDF parameter, and one
  trigger over `INSERT OR UPDATE OR DELETE` all behave as written.
* **`NEW.column` inside a PL/pgSQL trigger body fails at `CREATE TRIGGER` with `42P01`**
  (`no data source matches prefix: new in this context`). The parenthesised `(NEW).column`
  is accepted. This diverges from PostgreSQL and affects every trigger in the repository.
* **A PL/pgSQL function with a `DECLARE` block cannot be marked `STABLE`**:
  `22023: volatile statement not allowed in stable function: DECLARE`. `explain_refusal`
  therefore carries no volatility marker; its read-only property is enforced by there
  being no write statement in the body.
