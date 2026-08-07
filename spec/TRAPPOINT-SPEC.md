<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# TRAPPOINT — normative specification

**Version `1.0.0-rc.1`** · status: **release candidate** · licence: Apache-2.0

TRAPPOINT is a substrate for **gated subjects**: rows whose completion the database *refuses*
until every obligation attached to them carries a disposition the database itself typed. It is not
a library, not a service, and not a workflow engine. It is this document, a set of deterministic
SQL templates, and a conformance suite. The only meaning of the phrase *"TRAPPOINT-compliant"* is
**the conformance suite passes against your database**.

This document is the **public API**. It is versioned under the rule in [`VERSIONING.md`](VERSIONING.md):
*adding an invariant is a MAJOR bump*, because it breaks every deployed vertical.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, MAY and
OPTIONAL are to be interpreted as described in **RFC 2119** and **RFC 8174** when, and only when,
they appear in all capitals.

---

## 1. Scope, and the one thing this specification is about

A conventional integrity constraint is **synchronic**: it constrains the state of the row in front
of it. TRAPPOINT exists to make a **diachronic** condition — a condition over a subject's *ancestry*
and over facts held in *other rows* — enforceable by the same machinery, with the same finality,
against every writer including the database administrator and including any future application code.

Three properties follow, and every normative statement below serves one of them.

1. **The refusal is the product.** A gate that logs, warns, flags or notifies is out of scope. The
   only conformant outcome of an illegal history is a failed write with an **exact SQLSTATE and an
   exact exhibit name** ([`errors.md`](errors.md)).
2. **The refusal is total over writers.** A condition enforced in an application, an ORM, a stored
   procedure that a role may decline to call, or a trigger a role may `DISABLE`, is not enforced.
   Conformance is asserted against the *table*, by whatever writer, forever.
3. **The refusal is explainable.** A gate that only says "no" gets routed around, and an invariant
   that is routed around is not an invariant. Every refusal MUST be reducible to an irreducible
   reason set ([`wire/refusal.md`](wire/refusal.md)).

### 1.1 Out of scope, stated so nobody infers it

TRAPPOINT does not specify: how obligations are *discovered*; how severity is *scored*; retrieval,
ranking or embedding of any kind; the wire protocol between an application and the database; the
custody ledger (specified separately under `spec/custody/`); nor any human process. A vertical
supplies all of that. TRAPPOINT specifies only what the database must refuse and how the refusal
must be observable.

---

## 2. The kernel idiom — PROJECT · PIN · REFUSE

Everything in this specification compiles to three steps. They are not three implementation options;
they are one mechanism in three parts, and omitting any one of them makes the other two unsound.

> **PROJECT.** A row-level trigger writes a cross-row fact onto a **scalar column of the subject
> row**, derived from an **authoritative relation, never from the inserter**.
>
> **PIN.** A completed transition takes a **composite foreign key onto `(subject_id, epoch)`**. Any
> new obligation increments `epoch`. `ON UPDATE RESTRICT` makes attaching an obligation to a
> completed transition *physically impossible*.
>
> **REFUSE.** A **plain-column `CHECK`** over the projected scalar refuses the write, for every
> writer, forever.

### 2.1 PROJECT — normative

**P-1.** Every column read by a gate `CHECK` MUST be written by a trigger owned by the substrate.
No client-supplied value for such a column may survive the write; the trigger MUST overwrite it
unconditionally, whether or not the supplied value agrees.

**P-2.** The trigger MUST derive the value from a declared **authority source** — a relation named
in the vertical binding under `[[authority_source]]` — and MUST NOT derive it from the inserted row,
from another row of the same table, or from any relation the inserting role may write.

**P-3.** When the authority source holds no row for the subject, the trigger MUST refuse. It MUST
NOT default, MUST NOT infer, and MUST NOT pass. *Absence of evidence refuses; it never admits.*
The refusal is `P0001` naming the trigger function (§4), **unless** a constraint-backed refusal is
reachable by projecting the strictest legal values instead — in which case the trigger MUST project
the strictest values and let the constraint fire, because a constraint name is a better exhibit than
a message (§4.3, and see `I02`, `I10`).

**P-4.** A projected column MUST NOT be nullable. A `NOT NULL` projection left unset produces
`23502`, which is outside the refusal taxonomy and is therefore a conformance failure.

**P-5 (compile-time form).** A binding that declares a projected gate column without a matching
`[[authority_source]]` entry, or with `on_missing` set to anything other than `"raise"`, MUST cause
`trappoint render` to exit non-zero. See [`binding/authority-source.md`](binding/authority-source.md).
P-2 is thereby enforced before any SQL exists, not reviewed after it ships.

### 2.2 PIN — normative

**N-1.** A gated subject MUST carry a monotonically non-decreasing integer `gate_epoch`, and MUST
expose `UNIQUE (subject_id, gate_epoch)` as a foreign-key target.

**N-2.** Materialising a new obligation against a subject MUST increment that subject's `gate_epoch`
in the same transaction. Retracting a disposition MUST also increment it.

**N-3.** The record of a completed transition MUST hold a composite foreign key
`(subject_id, gate_epoch)` onto the subject, declared `ON UPDATE RESTRICT ON DELETE RESTRICT`.
`CASCADE` is forbidden in both positions: a cascade rewrites history, which is the precise offence
this specification exists to detect.

**N-4.** Consequence, and the reason the pin exists: once a completed transition references
`(subject_id, e)`, the database refuses **any** update that changes `gate_epoch`. Because every new
obligation must change it (N-2), **attaching an obligation to a completed subject is not a policy
violation — it is a referential-integrity violation.** The writer is forced onto the declared path:
suspend the completed subject and open a child whose gate is cleared afresh. That is branch
discipline expressed as referential integrity, and it is the correct structural answer to an anomaly
`SERIALIZABLE` provably cannot address (a fact arriving *after* commit is not a serialization
anomaly).

### 2.3 REFUSE — normative

**R-1.** Every gate condition expressible as a predicate over columns of a single row MUST be
declared as a `CHECK` constraint on that row's table. It MUST NOT be enforced by procedural code
alone, and procedural code MUST NOT pre-empt it (§4.3).

**R-2.** Each independently-nameable refusal MUST have its own `CHECK` with its own name. Collapsing
several conditions into one counter is non-conformant even where it is logically equivalent, because
**the constraint name is the exhibit**: *"the merge was refused by `boundary_certified_when_issued`"*
is a materially different sentence from *"a counter was non-zero"*, and one independent trigger per
counter is what makes the refusal-depth matrix (§6) meaningful.

**R-3 — Exhibit Uniqueness.** A refusal-bearing constraint, unique index or trigger-function name
MUST be unique across the whole database schema, not merely within its table. The exhibit name alone
MUST identify the refusal without a qualifying table. Where the same rule applies to two subject
kinds, the mirrored object takes a distinguishing prefix (`linear` / `cr_linear`,
`gate_closed_when_issued` / `cr_gate_closed_when_merged`, `substantive` / `carried_substantive`).

**R-4.** A gate condition that no `CHECK` can express — anything depending on `now()`, on an
aggregate over another table, or on the *absence* of a row — MUST be enforced by a trigger raising
`P0001` (§4), and MUST additionally be re-derived from base tables inside the transition procedure so
that a drifted projection is detected rather than trusted (§3.1, property 1).

---

## 3. The four kernel properties

Each is load-bearing; each is separately provable; none may be claimed without its proof artefact.

### 3.1 The projected counter is a materialised conflict

The projection trigger writes a real value to a real column of the subject row. Two transactions that
race — one materialising an obligation, one completing the transition — therefore contend on the same
row, not on a phantom. The gate stays welded **even if isolation is downgraded to `READ COMMITTED`**,
because the conflict is materialised in data rather than inferred by the isolation level.

*Proof artefact:* conformance case `CF-45` runs the entire gate history at `READ COMMITTED` and
asserts the same refusal, and `CF-43` asserts the concurrent interleaving yields `40001` on exactly
one of the two transactions.

*What this does NOT claim:* it does not claim `READ COMMITTED` is equivalent to `SERIALIZABLE` for
any other purpose. Counter-drift *detection* (§4.3) is weaker at `READ COMMITTED`, and a conformant
implementation MUST set the isolation level explicitly rather than inheriting it.

### 3.2 Refusal is structurally redundant

An illegal history must fail by more than one mechanism. The claim is proved by **unwelding**: the
harness disables one trigger, or drops one constraint, *one at a time*, re-runs the illegal history,
and asserts the write **still fails** — by a mechanism other than the one removed. The output is a
matrix of history × surviving mechanism, and `refusal_depth` is its row count.

> **This is the only place the structural-redundancy claim may be made.** At *runtime* the
> deterministic `RAISE` fires first, by construction, and no test, log, dashboard or document may
> assert redundancy from runtime behaviour. Reordering the mechanisms to "observe" the redundancy
> would make the observable SQLSTATE a race between constraint and foreign-key evaluation, which is
> unassertable — so the ordering is deliberate and the proof lives in CI.

**Normative:** every merge-gate history in the conformance manifest MUST carry
`refusal_depth_min >= 2`. An implementation whose depth is 1 for such a history is **non-conformant**,
and the pre-committed response is to remove the mechanism rather than ship it: a single-welded gate
is a claim that cannot be made under oath.

### 3.3 The ledger is gap-free by CAS, not by sequence

`CREATE SEQUENCE`, `nextval()`, `SERIAL` and `unique_rowid()` are **forbidden** anywhere in a
conformant implementation. Sequence allocations commit immediately and are not rolled back, so a
sequence gap means nothing and cannot be evidence of anything.

Instead, a monotone position is derived **inside** the transaction and committed under a uniqueness
constraint that acts as a lock-free compare-and-swap: `UNIQUE (subject, prev_seq)` for an event
chain, `PRIMARY KEY (site, seq)` for a ledger. Two concurrent writers from the same head collide on
`23505`. Therefore **a gap in a conformant chain means tampering**, which is the only reason to
number rows at all.

*Proof artefact:* `CF-14`, `CF-15`, `CF-17`, `CF-63`; and a repository-wide lint that fails on the
four forbidden constructs.

### 3.4 The gate is self-attesting

The source text of every gate object is snapshotted into an append-only attestation on every
migration and on every `ENABLE`/`DISABLE TRIGGER`, and a snapshot test forces a human to read the
gate's own source text in any diff that changes it. **Nobody can quietly weaken the gate that exists
to prevent quietly weakening controls.**

*Capability caveat, stated because honesty is cheaper than a retraction:* per-object granularity
requires `pg_get_triggerdef()` / `pg_get_functiondef()`. Where the platform gate for that capability
has not returned `PASS`, the binding MUST select the `show_create_table` fallback
(`capabilities.triggerdef`), the snapshot is marked `weak`, and the claim softens to table
granularity **in the same commit that selects the fallback**. See
[`binding/vertical.schema.json`](binding/vertical.schema.json).

---

## 4. The refusal contract, in brief

The full contract is [`errors.md`](errors.md). Three rules are normative here because the rest of the
specification depends on them.

### 4.1 The taxonomy is total

Over the gate path, exactly five SQLSTATEs are modelled:

| Code | Class | Meaning | Client behaviour |
|---|---|---|---|
| `40001` | RETRY | serialization failure | retried with capped exponential backoff and full jitter |
| `23514` | REFUSE | `CHECK` violation | attempted **exactly once, ever** |
| `23503` | REFUSE | foreign-key violation | attempted **exactly once, ever** |
| `23505` | REFUSE | unique violation | attempted **exactly once, ever** |
| `P0001` | REFUSE | `RAISE` from substrate procedural code | attempted **exactly once, ever** |

Any other SQLSTATE observed on the gate path is a **conformance failure**, because it means the
database refused for a reason nobody modelled. `42501` is not on the gate path — it is a *pre-gate*
denial and belongs to the DENY class (`errors.md` §3).

### 4.2 A refusal is never retried

A conformant client MUST NOT retry `23514`, `23503`, `23505` or `P0001`. Not with backoff, not once,
not "in case it was transient". A blanket-retry helper (`tenacity`, `backoff`, `retrying` or a
hand-rolled equivalent applied to the gate path) makes the implementation **non-conformant**,
because it converts a refusal into a load test against a constraint and destroys the "attempted
exactly once" property that makes the refusal ledger evidence.

### 4.3 Synthetic codes are forbidden

**S-RULE.** Substrate procedural code — a trigger function, a UDF or a procedure — MUST NOT `RAISE`
with SQLSTATE `23514`, `23503`, `23505` or `40001`. All deterministic refusals originating in
procedural code use `P0001`.

Two reasons, both operational rather than aesthetic:

- `diag.constraint_name` is **empty** on a synthetic raise. The constraint name is the exhibit; a
  raise that impersonates `23514` produces an exhibit with no name.
- A synthetic `40001` is indistinguishable from a real serialization failure, so a conformant client
  would retry a deterministic refusal forever.

**Corollary — the re-derivation rule.** Where a condition is *also* expressible as a `CHECK` over a
projected scalar, procedural code MUST NOT pre-empt the `CHECK`. It re-derives the condition from
base tables and raises `P0001` **only** on *drift* — the derived value disagreeing with the projected
value — or on a condition no `CHECK` can hold. The refusal a conformant history observes for an open
obligation is therefore `23514` on the named `CHECK`, never a synthetic code.

**Worked example.** A disposition whose `(virulence, kind)` pair is not a legal clearance must fail
with `23503` on `fk_clearance`. The projection trigger therefore does **not** raise when its
`clearance_legal` lookup misses; it projects the *strictest* legal values (`req_* = true`,
`min_signer_rank` at maximum), returns the row, and lets the real composite foreign key fire with its
name attached. This also avoids `23502`, which P-4 forbids.

---

## 5. The gated-subject state machine contract

### 5.1 Definitions

A **gated subject** is a row that (a) carries a state column drawn from a closed alphabet, (b) carries
`gate_epoch` per N-1, (c) carries one or more projected obligation counters, and (d) whose completing
state is defended by at least one `CHECK` over those counters.

An **obligation** is a row referencing a gated subject that must be *disposed* before the subject may
complete. Its wire shape is [`wire/obligation.md`](wire/obligation.md).

A **disposition** is a row that closes exactly one obligation, whose legal kinds are a function of a
projected classification of the obligation, enforced by composite foreign key.

A **completion record** is the row that pins the transition per N-3.

### 5.2 The alphabet and the edge set

A conformant vertical MUST hold its legal transitions as **queryable data**, not as procedural logic:
a table `subject_transition (subject_kind, from_state, to_state)` with that primary key, and a
foreign key from the subject's event chain onto it. An illegal transition is then `23503` on a named
constraint, not an `if` statement a future commit can delete.

The reference alphabet, which every subject kind in a binding shares:

```
draft ─────────────► checks_materialised ──┬──► dispositioned ──┬──► merged ──┬──► suspended ──► closed
  │                        ▲               │                    │            │
  │                        └───────────────┘                    │            └──► closed
  └──► abandoned                                                └──► checks_materialised
```

Normatively, as edges:

| from | to | note |
|---|---|---|
| `draft` | `checks_materialised` | the first obligation materialises |
| `draft` | `abandoned` | nothing was ever gated |
| `checks_materialised` | `checks_materialised` | a further obligation arrives; `gate_epoch` increments |
| `checks_materialised` | `dispositioned` | every obligation carries a live disposition |
| `dispositioned` | `checks_materialised` | a late obligation, or a retraction, re-opens the gate |
| `dispositioned` | `merged` | **the gated transition** |
| `merged` | `suspended` | a post-completion fact forces a fork |
| `merged` | `closed` | terminal |
| `suspended` | `closed` | terminal |

**MUST:** there is no edge into `merged` from anywhere but `dispositioned`, and no edge out of
`merged` except `suspended` and `closed`. There is no edge from `merged` back to any open state:
completion is not reversible, and a vertical that needs to reverse one opens a child subject.

### 5.3 The transition procedure

The completing transition MUST be performed by a substrate-owned procedure invoked in a single round
trip, and its statement order is normative because `DEFERRABLE INITIALLY DEFERRED` constraints are
unavailable on the target platform — **every intermediate state must be legal at statement
boundaries**:

1. lock the subject row (`SELECT … FOR UPDATE`) — for lock ordering and retry-thrash reduction
   **only, never for correctness**; the correctness argument is the materialised conflict (§3.1);
2. test the projected counters;
3. **re-derive** the counters from base tables (§4.3) and refuse `P0001` on drift;
4. append the event row at `seq = head + 1, prev_seq = head` — `23505` means someone moved the head;
5. insert the completion record at the current `gate_epoch` — the composite FK pins it (N-3);
6. write the custody entry;
7. **last**, update the subject to the completing state, so the `CHECK`s fire on the final write.

A conformant implementation MUST NOT complete the transition in step 1–6 order rearranged such that
the subject reaches the completing state before the completion record exists.

### 5.4 Two subject kinds, one kernel

A binding MAY declare more than one gated subject kind. Where it does, each kind carries its own
mirrored constraint set under R-3, and a completion record table shared across kinds MUST use one
nullable subject reference per kind plus a composite foreign key per kind (a composite FK containing
a NULL column is not enforced under MATCH SIMPLE, which is exactly the required "one per kind"
behaviour), with a `CHECK` binding the polymorphic `subject_id` to whichever reference is non-null.

---

## 6. Conformance

An implementation is **TRAPPOINT-conformant at version `X.Y.Z`** if and only if:

- **C-1.** Every case in [`conformance/manifest.toml`](conformance/manifest.toml) whose `profiles`
  include the implementation's profile either passes with the exact `expect_sqlstate` **and** exact
  `expect_constraint` recorded there, or is skipped with a machine-readable reason drawn from its
  `requires` list.
- **C-2.** No case observes a SQLSTATE outside the taxonomy for its class (§4.1).
- **C-3.** Every case with `refusal_depth_min >= 2` achieves at least that depth under the unwelding
  harness (§3.2).
- **C-4.** `trappoint render --check` is a zero-diff no-op: the committed SQL is exactly what the
  templates and the binding produce.
- **C-5.** The binding validates against [`binding/vertical.schema.json`](binding/vertical.schema.json),
  and every `@projects` pragma in a rendered template has a matching `[[authority_source]]` with
  `on_missing = "raise"`.
- **C-6.** Every refusal surfaced to a client validates against
  [`wire/refusal.schema.json`](wire/refusal.schema.json).

A claim of conformance MUST cite the spec version and the profile, e.g.
*"TRAPPOINT conformance 1.0, profile `trappoint-ref`, 45/45, refusal-depth min 2"*. A claim without a
profile is not a claim.

### 6.1 What conformance does not certify

It does not certify that the *vertical's* obligations are the right obligations, that severity was
scored correctly, that a disposition is honest, or that the humans understood what they signed. It
certifies that the database refused what this document says it must refuse. Everything else is a
vertical's problem and this specification declines to imply otherwise.

---

## 7. The sixteen invariants

Each has a normative file under [`invariants/`](invariants/) carrying the same five sections:
**NORMATIVE STATEMENT** · **MECHANISM** · **OBSERVABLE** · **CONFORMANCE** · **NOT CLAIMED**.

| ID | Invariant | One line |
|---|---|---|
| [`I01`](invariants/I01-append-only.md) | Append-only | evidentiary tables admit inserts and one declared retraction; nothing else |
| [`I02`](invariants/I02-projected-refusal.md) | Projected refusal | every cross-row gate condition is a trigger-maintained scalar under a `CHECK` |
| [`I03`](invariants/I03-epoch-pin.md) | Epoch pin | a completed transition pins `(subject, epoch)`; new obligations bump the epoch |
| [`I04`](invariants/I04-linear-head.md) | Linear head | `UNIQUE (subject, prev_seq)` CAS; no forks, even at `READ COMMITTED` |
| [`I05`](invariants/I05-ancestry-monotone.md) | Ancestry monotone | a child's ancestry commitment extends its parent's; inherited severity never decreases |
| [`I06`](invariants/I06-derived-dependency.md) | Derived dependency | a dependency edge consumed by a gate is computed, never declared |
| [`I07`](invariants/I07-universe-commitment.md) | Universe commitment | a retrieval informing a gate commits to its universe before any disposition cites it |
| [`I08`](invariants/I08-certified-null.md) | Certified null | an empty result is representable only with a coverage certificate |
| [`I09`](invariants/I09-exposure-binding.md) | Exposure binding | a disposition exists only against a precursor materialised to *that* actor |
| [`I10`](invariants/I10-typed-clearance.md) | Typed clearance | the legal verdict set is a function of ancestral severity, by composite FK |
| [`I11`](invariants/I11-evidence-typing.md) | Evidence typing | a prior approval is not evidence; a gist match may not clear |
| [`I12`](invariants/I12-no-decay-without-evidence.md) | No decay without evidence | no elevated state de-escalates by timeout |
| [`I13`](invariants/I13-silence-logged.md) | Silence is logged | every declined surfacing is written with its arithmetic, in the same transaction |
| [`I14`](invariants/I14-minimal-refusal.md) | Minimal refusal | every refusal emits an irreducible reason set and, where computable, an alternative |
| [`I15`](invariants/I15-allegation-firewall.md) | Allegation firewall | no substrate table stores a score characterising a named human |
| [`I16`](invariants/I16-external-witness.md) | External witness | no checkpoint is admissible without cosignatures across ≥ k trust domains, ≥ 1 adverse |

**Extension.** A vertical MUST NOT renumber, redefine or extend `I01–I16`. A vertical's own schema
invariants live in its own namespace (`MAINLINE` uses `MI01–MI30`) and map *onto* these; the mapping
is data, in the vertical's own catalogue, not in this document.

**Namespace.** The identifier pattern `I<dd>` is reserved to `spec/`, enforced by a repository-wide
lint that is *defined by its grep command* rather than described
([`VERSIONING.md`](VERSIONING.md) §3.1). Outside `spec/`, an invariant is cited by **slug** —
`TRAPPOINT/projected-refusal`, not `I02` — because no exemption for a qualified or linked identifier
survives contact with the command that enforces the rule. The slug table is `VERSIONING.md` §3.2.

---

## 8. Versioning

Summarised here; normative in [`VERSIONING.md`](VERSIONING.md).

| Change | Bump |
|---|---|
| adding, removing or restating an invariant so an implementation that passed can fail | **MAJOR** |
| tightening any MUST; adding a required field to a wire schema; adding a required binding key | **MAJOR** |
| renaming an exhibit (constraint / trigger / index name) | **MAJOR** |
| a new **optional** extension point: an optional binding key, an optional wire field, a new capability switch, a new profile | **MINOR** |
| adding a conformance case that only fails implementations already violating an existing MUST | **MINOR** |
| documentation, rationale, examples, performance guidance, error *message* text | **PATCH** |
| correcting a manifest's `expect_constraint` to the name the platform actually reports | **PATCH** |

Adding an invariant is MAJOR **because it breaks every deployed vertical**, not because the document
grew. That asymmetry is the whole reason the catalogue is small and closed.

---

## 9. Normative references

- RFC 2119 / RFC 8174 — requirement keywords.
- RFC 8785 — JSON Canonicalisation Scheme, used by the custody layer (`spec/custody/`).
- RFC 6962 §2.1 — Merkle tree leaf/interior hashing, used by the custody layer.
- ISO/IEC 9075 — `SQLSTATE` class and subclass values referenced in [`errors.md`](errors.md).
- `spec/conformance/manifest.toml` — the machine-readable conformance suite, which is **normative**
  wherever it disagrees with prose in this document.

---

*A suite that has never been red asserts nothing. A refusal with no name is not an exhibit.*
