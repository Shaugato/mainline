<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# 01 · The mechanism — PROJECT, PIN, REFUSE

> **You are here:** chapter 1 of 5 — start at the [front door](../ARCHITECTURE.md). Terms link to
> the [glossary](GLOSSARY.md) on first use. No prior knowledge of this project is assumed.

---

## Sixty seconds

Three nouns carry this whole system, and none of them is a database term.

A [**permit**](GLOSSARY.md#permit) is a written authorisation for one specific dangerous job, at one
place, for one window of time. Nobody starts work until it is issued. An
[**obligation**](GLOSSARY.md#obligation) — the table calls it a blocking check — is something that
must be settled before the permit may be issued; usually a past incident this job resembles,
attached to this permit as its own row. A [**disposition**](GLOSSARY.md#disposition) is the signed
answer to exactly one obligation: a named, competent person recording what they did about it.

The dangerous moment is the [**issue**](GLOSSARY.md#merge) — the instant the permit stops being a
draft and becomes an authorisation somebody works under. This chapter defends that one write.

The [gate](GLOSSARY.md#gate) is one idea in three parts:

- **PROJECT** — when an obligation is attached, the database itself writes a number onto the permit
  row. Not the application. The database. That number is a [projection](GLOSSARY.md#projection).
- **PIN** — a permit that has been issued is nailed to the exact set of obligations it was issued
  against, by a foreign key ([epoch pin](GLOSSARY.md#pin)). Attaching a new obligation to it
  afterwards is not against the rules; it is impossible.
- **REFUSE** — a plain `CHECK` constraint reads that number and refuses to let the permit reach the
  issued state while it is non-zero. For every writer. Including a future release of our own code.
  Including the administrator.

That is it. The refusal is not a warning, a flag, a log line or a notification. It is a failed write
with a five-character code — a [SQLSTATE](GLOSSARY.md#sqlstate) — and a constraint name attached. On
the live system that sentence is `23514` on `gate_closed_when_issued`
[src: evidence/gate-refusal/proof-20260810T054407Z.json#refusal.constraint]. The rest of this chapter
says that three times more precisely, then answers the question an engineer asks immediately: *why
the database, and not the application?*

---

## 1. Three nouns, before any rule

### 1.1 A permit

The row is `mainline.permit`
([`0050_permit.sql`](../../verticals/mainline/db/migrations/0050_permit.sql)). It carries who,
where, until when, and a `state` column drawn from a closed list of words — `draft`,
`checks_materialised`, `dispositioned`, `merged`, `suspended`, `closed`
([spec §5.2](../../spec/TRAPPOINT-SPEC.md)). The completing state is spelled `merged`, and the
spelling is deliberate: this is a protected branch, and issuing a permit is a merge.

There is no edge into `merged` from anywhere except `dispositioned`, and no edge out of it except
`suspended` and `closed` (§5.2, the MUST after the edge table). Issuing is not reversible. A permit
that must change after issue is suspended, and a **child** permit is opened whose gate is cleared
from scratch.

### 1.2 An obligation

The row is `mainline.blocking_check`
([`0058_blocking_check.sql`](../../verticals/mainline/db/migrations/0058_blocking_check.sql)). It
names the permit it blocks and the version of the [clause](GLOSSARY.md#clause) — one numbered rule
inside a procedure — that it came from. Its severity is **not** supplied by whoever creates it; the
file's own header gives the reason: *"the agent that proposes an obligation cannot talk it down"*
(`0058_blocking_check.sql:8-9`). It is looked up from an authority relation and written over the top
of whatever arrived. An obligation stays open until a *live* disposition covers it, and "live"
carries a time condition — an expired disposition stops covering its obligation, untouched.

### 1.3 A disposition

The row is `mainline.disposition`
([`0066_disposition.sql`](../../verticals/mainline/db/migrations/0066_disposition.sql)). It closes
exactly one obligation. The signer's rank, organisation and competency digest are looked up from the
person record and written onto the row by the database, so a client claiming a rank it does not hold
has the row corrected before any rule is evaluated (`0066_disposition.sql:44-48`). Which kinds of
answer are legal is not a matter of judgement either: it is a composite foreign key into a clearance
table, so at a severity inherited from the incident's [ancestry](GLOSSARY.md#ancestry) some answers
do not exist as rows at all, and attempting one is `23503` naming `fk_clearance`.

### 1.4 The one moment being defended

Draft a permit, attach obligations, sign dispositions — none of that is dangerous. The dangerous
write is the single `UPDATE` that moves `state` to `merged`. From here on, "the gate" means the set
of database objects that refuse **that** write.

---

## 2. One mechanism, three parts

The specification's own framing: *"They are not three implementation options; they are one mechanism
in three parts, and omitting any one of them makes the other two unsound"*
([spec §2](../../spec/TRAPPOINT-SPEC.md)).

### 2.1 PROJECT — the counter belongs to the database

**In plain terms.** When an obligation is attached to a permit, a trigger fires and writes a number
onto the permit row itself. The number is derived from other rows, and it overwrites whatever the
writer supplied, whether or not the supplied value happened to be right.

**Why that is the whole point.** A counter a client writes is a client's opinion. A counter a trigger
writes is the database's. Everything downstream — the constraint, the refusal, the exhibit — is only
worth as much as the provenance of that number, so the number is taken away from the writer entirely.
This is a **projection**: a value the database maintains on a row by itself, derived from elsewhere.

**Where it is.** The column is `mainline.permit.open_blocking`
(`0050_permit.sql:94`), one of seven projected counters on that table (`:93-101`). The trigger is
`check_materialised`, welded `AFTER INSERT ON mainline.blocking_check`
(`0121_trg_check_materialised.sql:30`), running
[`mainline.fn_check_materialised()`](../../verticals/mainline/db/migrations/0101_fn_check_materialised.sql).
Its body does the two increments in one statement (`0101_fn_check_materialised.sql:62-65`):

```sql
UPDATE mainline.permit
   SET open_blocking = open_blocking + 1,
       gate_epoch    = gate_epoch + 1
 WHERE permit_id = (NEW).permit_id;
```

**The normative rules**, from [spec §2.1](../../spec/TRAPPOINT-SPEC.md):

| Rule | What it requires |
|---|---|
| **P-1** | Every column a gate `CHECK` reads MUST be written by a substrate-owned trigger, and the trigger MUST overwrite the client's value unconditionally — *"so that a correct guess confers no privilege"* (`spec/invariants/I02-projected-refusal.md:23-24`). |
| **P-2** | The value MUST come from a declared authority relation, and MUST NOT come from the inserted row, from a sibling row, or from anything the inserting role can write. |
| **P-3** | When the authority relation holds **no row**, the trigger MUST refuse. Not default, not infer, not admit-and-flag. *Absence of evidence refuses.* |
| **P-4** | A projected column MUST NOT be nullable. A `NOT NULL` projection left unset yields `23502`, which is outside the modelled refusal taxonomy and is therefore a conformance failure. |
| **P-5** | This is checked before any SQL exists: a binding that declares a projected gate column with no matching `[[authority_source]]`, or with `on_missing` set to anything but `"raise"`, makes `trappoint render` exit non-zero. |

**The measured instance.** One `INSERT INTO mainline.blocking_check`, with no other statement between
the before and after readings, moved `open_blocking` from `0` to `1`
[src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.open_blocking.before]
[src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.open_blocking.after] and
`gate_epoch` from `0` to `1`
[src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.gate_epoch.before]
[src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.gate_epoch.after]. In the same
write, the script supplied a severity of `0` and the database stored `4`
[src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.severity.supplied_by_this_script]
[src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.severity.projected_onto_the_check].
That last pair is P-1 as an observation rather than as a sentence: the writer's number did not
survive, and it produced no error and no warning. It was simply replaced.

### 2.2 PIN — a fact that arrives after the decision

**In plain terms.** The permit carries a counter, [`gate_epoch`](GLOSSARY.md#epoch), that goes up
every time a new obligation arrives. When the permit is issued, the record of that issue takes a
foreign key onto the pair `(permit_id, gate_epoch)` — the permit *and* the exact epoch it was issued
at. That key is declared `ON UPDATE RESTRICT`: the database will refuse any update that changes the
epoch, and every new obligation must change it.

**The sentence that earns this section.** Once a permit is issued at epoch `e`, attaching a new
obligation to it is not a policy violation. It is a referential-integrity violation. The rule is not
"you may not do this"; the rule is that there is no way to express it.

The writer is therefore forced onto the declared path — suspend the issued permit, open a child, let
the child's gate be cleared afresh. That is branch discipline expressed as referential integrity, and
`0071a_epoch_pin_permit.sql:10-17` says it in the file's own words: *"a precursor inserted after a
merge is a perfectly serializable history."*

**Why isolation cannot do this job.** `SERIALIZABLE` guarantees that concurrent transactions produce
a result equivalent to running them one after another. A fact that arrives an hour after the permit
was issued is not concurrent with anything. There is no interleaving to forbid, no anomaly to detect,
and nothing for the isolation level to say. The spec puts it flatly: the pin is *"the correct
structural answer to an anomaly `SERIALIZABLE` provably cannot address"*
([spec §2.2, N-4](../../spec/TRAPPOINT-SPEC.md)).

**Where it is.** The foreign-key target is `CONSTRAINT permit_epoch_target UNIQUE (permit_id,
gate_epoch)` (`0050_permit.sql:142`). The pin itself is
[`0071a_epoch_pin_permit.sql:35-39`](../../verticals/mainline/db/migrations/0071a_epoch_pin_permit.sql):

```sql
ALTER TABLE mainline.merge_record
  ADD CONSTRAINT epoch_pin_permit
  FOREIGN KEY (permit_id, gate_epoch)
  REFERENCES mainline.permit (permit_id, gate_epoch)
  ON UPDATE RESTRICT ON DELETE RESTRICT;
```

**The normative rules**, from [spec §2.2](../../spec/TRAPPOINT-SPEC.md):

| Rule | What it requires |
|---|---|
| **N-1** | The subject carries a non-decreasing integer `gate_epoch` and exposes `UNIQUE (subject_id, gate_epoch)` as a foreign-key target. |
| **N-2** | Materialising a new obligation MUST increment the epoch in the same transaction. Retracting a disposition MUST increment it too. |
| **N-3** | The record of the completed transition holds the composite foreign key `ON UPDATE RESTRICT ON DELETE RESTRICT`. `CASCADE` is forbidden in both positions, because *"a cascade rewrites history, which is the precise offence this specification exists to detect"*. |
| **N-4** | The consequence above: attaching an obligation to a completed subject is a referential-integrity violation, and the remedy is a fork. |

**What the pin does not claim.** It does not stop the fact from arriving. A precursor discovered after
issue is real, and the world does not care about our foreign keys. What the pin makes impossible is
back-fitting that fact into a closed decision so the record reads as though it had been considered.
It also does not close the operational window between discovery and the crew being told — that is an
operations problem, and no schema retires it
(`spec/invariants/I03-epoch-pin.md:81-87`).

### 2.3 REFUSE — and why the constraint's *name* is the exhibit

**In plain terms.** A `CHECK` constraint reads the projected counter and refuses the write. A `CHECK`
over a plain column of the row being written is the most ordinary thing in SQL, which is exactly why
it was chosen: it applies to every writer, through every connection, forever, with no cooperation
required from anyone.

**Where it is** (`0050_permit.sql:114`):

```sql
CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0)
```

Read it as English: *the permit may be in any state at all while obligations are open; the one state
it may not be in is issued.*

**The normative rules**, from [spec §2.3](../../spec/TRAPPOINT-SPEC.md):

| Rule | What it requires |
|---|---|
| **R-1** | Any gate condition expressible as a predicate over one row MUST be a `CHECK` on that row's table. Not procedural code, and procedural code MUST NOT pre-empt it. |
| **R-2** | Each independently nameable refusal gets its **own** `CHECK` with its **own** name. Collapsing several into one counter is non-conformant *even where it is logically equivalent*. |
| **R-3** | Refusal-bearing names are unique across the whole schema, not merely within a table, so the name alone identifies the refusal without a qualifying table. |
| **R-4** | A condition no `CHECK` can express — anything over `now()`, over an aggregate, or over the *absence* of a row — is enforced by a trigger raising `P0001`, and is re-derived from base tables so a drifted projection is detected rather than trusted. |

**Why R-2 is worth its cost.** One counter would enforce the rule with less code. Seven independently
named constraints exist instead (`0050_permit.sql:113-124`) because *"the merge was refused by
`gate_closed_when_issued`"* is a materially different sentence from *"a counter was non-zero"*. The
first names what was wrong. The second names an implementation detail. When the question is asked
eighteen months later by somebody who does not have the source open, only the first sentence is worth
anything. The file's own header calls the constraint name the courtroom exhibit
(`0050_permit.sql:15`).

**R-4, and the one arm you can see fire.** `mainline.fn_permit_merge_gate()`
([`0115_fn_permit_merge_gate.sql`](../../verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql))
re-counts the open obligations from the base tables at issue time, and raises `P0001` only when the
re-derived count disagrees with the projected counter — only on [**drift**](GLOSSARY.md#drift)
(`0115_fn_permit_merge_gate.sql:76-81`). It declines to refuse anything the `CHECK` can refuse: a
synthetic code carries no constraint name and would trade a named exhibit for an unnamed one (spec
§4.3). Measured: with `open_blocking` forced to zero out of band and the obligation still open, the
observed refusal was `P0001` on `mainline.fn_permit_merge_gate`
[src: evidence/gate-refusal/proof-20260810T054407Z.json#drift_refusal.sqlstate]
[src: evidence/gate-refusal/proof-20260810T054407Z.json#drift_refusal.constraint].

Five codes are modelled on this path and no others (spec §4.1): `40001` retry · `23514` a `CHECK`
refused · `23503` a foreign key refused · `23505` a uniqueness violation · `P0001` a raise from
substrate code. Anything else appearing here means the database refused for a reason nobody modelled,
and that is itself a conformance failure. A refusal is **never** retried (spec §4.2) — retrying it
would convert a decision into a load test against a constraint.

### 2.4 Why all three, or none

Drop **PROJECT** and the `CHECK` reads a number the writer chose. Drop **REFUSE** and the number is
maintained honestly and consulted by nobody. Drop **PIN** and both hold perfectly at the moment of
issue, and are silently falsified an hour later by an `INSERT` that nobody has to lie to perform.

---

## 3. The four kernel properties, and what each does *not* claim

Spec §3 states four properties. Each is separately provable, and the spec's own rule is that *"none
may be claimed without its proof artefact"* — where the artefact is normally a case in the
[conformance suite](GLOSSARY.md#conformance). Section 3.5 states which of the four has one here.

### 3.1 The projected counter is a materialised conflict

**Plainly.** Two things happening at once — someone attaching an obligation, someone issuing the
permit — touch the *same row*, because the counter lives on the permit. They collide on real data,
not on an inference the database has to be clever enough to draw.

**Precisely.** Because the conflict is materialised in data rather than inferred by the isolation
level, the gate stays welded even if isolation is downgraded to `READ COMMITTED`
([spec §3.1](../../spec/TRAPPOINT-SPEC.md)).

**What this does NOT claim.** It does not claim `READ COMMITTED` is equivalent to `SERIALIZABLE` for
any other purpose. Drift *detection* (§2.3, R-4) is weaker at `READ COMMITTED`, and a conformant
implementation must set its isolation level explicitly rather than inherit it.

### 3.2 Refusal is structurally redundant — and the honest status of that claim

**Plainly.** The ambition is that an illegal history fails by more than one mechanism, so that
removing any single one still leaves the write refused.

**Precisely, and this is the part that constrains us.** The claim is provable in exactly one way:
by **unwelding**. A harness disables one trigger, or drops one constraint, *one at a time*, re-runs
the identical illegal history in a fresh tenancy, and asserts the write still fails — by a mechanism
other than the one removed
([`packages/trappoint-conformance/unweld/harness.py`](../../packages/trappoint-conformance/unweld/harness.py),
[`unweld/mutations.py`](../../packages/trappoint-conformance/unweld/mutations.py)). At runtime the
deterministic `RAISE` fires first by construction, so **no test, log, dashboard or document may
assert redundancy from runtime behaviour** (spec §3.2, and `unweld/harness.py:4-8`).

**What this build claims: nothing.** The committed matrix
[`packages/trappoint-conformance/REFUSAL_DEPTH.md`](../../packages/trappoint-conformance/REFUSAL_DEPTH.md)
records **9 of 9 gated merge-gate histories measured at [depth](GLOSSARY.md#refusal-depth) 1** —
below the declared floor of two (`REFUSAL_DEPTH.md:19`, `:123-133`). That matrix was measured on the
reference profile with six stand-in relations supplied so the tree would apply at all
(`REFUSAL_DEPTH.md:15`), and in CI the unwelding lane has never reached its own pytest step at all —
it dies earlier, at `trappoint migrate up` ([`docs/CI-STATE.md`](../CI-STATE.md) §5.8,
`docs/CI-STATE.md:1248-1268`). *Did not run* and *ran and failed* are different findings, and both
are on the record. So this document does not claim the gate is redundantly welded. It claims the
property is specified, that the only admissible proof of it is built and committed, and that the
number it currently returns is one. The pre-committed response to a depth of one is on the record
and is not to relax the floor — *cut the mechanism, do not ship it* (`REFUSAL_DEPTH.md:121`).

### 3.3 The ledger is gap-free by compare-and-swap, not by sequence

**Plainly.** Numbered rows are only evidence if a missing number *means* something. A database
sequence cannot carry that meaning: it hands out a number, and if the transaction rolls back the
number is spent anyway. A gap in a sequence means nothing at all.

**Precisely.** `CREATE SEQUENCE`, `nextval()`, `SERIAL` and `unique_rowid()` are forbidden anywhere
in a conformant implementation (spec §3.3), enforced by a repository lint that refuses them in every
migration file and every rendered template
([`packages/trappoint-migrate/src/trappoint_migrate/lint.py:110-125`](../../packages/trappoint-migrate/src/trappoint_migrate/lint.py)).
The position is instead derived *inside* the transaction and committed under a uniqueness constraint
that behaves as a lock-free compare-and-swap — `CONSTRAINT linear UNIQUE (permit_id, prev_seq)`
(`0059_permit_event.sql:70`). Two writers starting from the same head collide on `23505`. Therefore a
gap in a conformant chain means tampering, which is the only reason to number rows at all.

**Measured on this build.** The three event-chain cases pass — `CF-14` *"Two permit_event rows
appended from the same head"*, `CF-15` *"Two cr_event rows appended from the same head"*, `CF-17`
*"Append a permit_event declaring a prev_seq with no predecessor row"*
[src: qa/conformance-census.json#cases[id=CF-14].status]
[src: qa/conformance-census.json#cases[id=CF-15].status]
[src: qa/conformance-census.json#cases[id=CF-17].status]. The custody-ledger case does not: `CF-63`
*"Write two ledger leaves at the same sequence position"* expected `23505` on `ledger_leaf_pkey`,
observed `00000`, the write completed
[src: qa/conformance-census.json#cases[id=CF-63].status]. The census's own words for that outcome:
*"A gate that admits this write is not a gate."*

**What this does NOT claim.** The CAS property is demonstrated for the subject event chains and is
**not** demonstrated for the [custody](GLOSSARY.md#custody) ledger leaf on this build. Custody —
the separate machinery for proving evidence has not been altered since — has its own proof status,
and [chapter 5](05-what-is-not-built.md) carries the full account.

### 3.4 The gate is self-attesting

**Plainly.** The danger is not that somebody changes the gate. It is that somebody changes the gate
**and the diff does not show it** — a migration called `0154_widen_a_column.sql` that happens to
replace a trigger function produces a review in which the reviewer reads a column widening
(`packages/trappoint-conformance/tests/test_gate_source_snapshot.py:4-9`).

**Precisely.** The gate's own source text, *as the server reports it*, is committed as a snapshot at
[`packages/trappoint-conformance/tests/__snapshots__/gate_source.sql`](../../packages/trappoint-conformance/tests/__snapshots__/gate_source.sql),
and any change to what the database actually executes appears as a diff in a file whose name is the
sentence *"the gate changed"*. It cannot be updated without an explicit flag and a reviewer seeing
before and after.

**The capability caveat, stated because honesty is cheaper than a retraction.** Per-object
granularity requires `pg_get_triggerdef()` and `pg_get_functiondef()`. Both were measured working on
CockroachDB `v26.2.5` while that suite was written
(`packages/trappoint-conformance/tests/test_gate_source_snapshot.py:25-30`), so this snapshot is the
strong form. Where a platform lacks them the binding must select the `SHOW CREATE TABLE` fallback,
the snapshot is marked `weak` in its own header, and the claim softens to table granularity **in the
same commit that selects the fallback** (spec §3.4).

**What this does NOT claim.** A snapshot proves the executing text changed. It does not prove the
change was reviewed competently, and it does not prevent a change — it prevents a change from being
invisible. The CI lane that runs this suite is one of the two lanes recorded as **UNPROVEN** rather
than passing, because it never reaches its own subject (`docs/CI-STATE.md:677-688`).

### 3.5 Proof status of the four properties, on this build

| Property | Its declared proof artefact | Status here |
|---|---|---|
| 3.1 materialised conflict | `CF-45` (whole history at `READ COMMITTED`), `CF-43` (concurrent interleaving → `40001`) | **not demonstrated** — both are `cannot_run` in the census: the *legal* world could not be built, at `clause_version`, column `body_sha256` does not exist [src: qa/conformance-census.json#cases[id=CF-45].status] |
| 3.2 structural redundancy | the unwelding matrix | **measured at depth 1**, below the floor of 2, and the CI lane has never run (`REFUSAL_DEPTH.md:19`) |
| 3.3 gap-free by CAS | `CF-14`, `CF-15`, `CF-17`, `CF-63`, plus the lint | **three passed, `CF-63` failed** [src: qa/conformance-census.json#cases[id=CF-63].status] |
| 3.4 self-attesting | the committed gate-source snapshot | **artefact committed**; the lane that would re-run it is UNPROVEN, not green |

Census totals for the whole suite on that run: 71 declared · 10 passed · 6 failed · 55 could not run
[src: qa/conformance-census.json#totals.passed]
[src: qa/conformance-census.json#totals.failed]
[src: qa/conformance-census.json#totals.cannot_run] — profile `mainline`, spec `1.0.0-rc.1`, cluster
`CockroachDB CCL v26.2.5`, generated `2026-08-10T07:59:48Z`
[src: qa/conformance-census.json#run.generated_at]. A first census, not a passing suite; chapter 5
accounts for the whole of it.

**One tension a careful reader will find, stated here rather than left to be discovered.** The
flagship refusal is proven: the gate-refusal proof observes `23514` on `gate_closed_when_issued`,
verdict `PROVEN`, caveats empty
[src: evidence/gate-refusal/proof-20260810T054407Z.json#verdict]
[src: evidence/gate-refusal/proof-20260810T054407Z.json#caveats|len]. The conformance case that
asserts that same refusal, `CF-01`, is **failed** in the census — it observed `23502` on a `NOT NULL`
column `site_role` that a trigger left unset, which is precisely what spec rule **P-4** forbids
[src: qa/conformance-census.json#cases[id=CF-01].status]. Both statements are true of different runs
against different worlds. The gate refuses; the conformance case that certifies the refusal does not
currently pass. Neither sentence is allowed to stand in for the other.

---

## 4. Why the database, and not the application

This is the question every engineer asks, and it deserves the argument rather than an assertion.

**The requirement is not "the check runs". It is "the check cannot not run".** Spec §1 property 2
puts it in one sentence: *"A condition enforced in an application, an ORM, a stored procedure that a
role may decline to call, or a trigger a role may `DISABLE`, is not enforced."* Each of those homes
fails differently, and the differences are the argument.

| Where the rule lives | Who it binds | How it fails |
|---|---|---|
| in the application | writers that take that code path | a second service, a data-migration script, an incident-response `psql` session at 03:00, a vendor integration, a feature written next year by somebody who has never read this page — none take that path. The rule was enforced against a *code path*, and code paths multiply. |
| in an ORM or shared library | writers that import it | the first writer that does not import it is not detected as a violation. It is simply not covered, and nothing anywhere reports that fact. |
| in a stored procedure | callers that call it | a role holding `INSERT` and `UPDATE` on the table can decline to call it and write the row directly. The same failure as the application one, moved inside the database. |
| in a trigger alone | every writer, until someone runs `DISABLE TRIGGER` | and its refusal is a raise, so `diag.constraint_name` is empty (spec §4.3). An exhibit that is a sentence inside a string is a weaker artefact than an exhibit that is the name of a database object. |

**In a `CHECK` constraint over a projected scalar.** A `CHECK` is evaluated by the storage layer on
the write itself. There is no path around it that is still a write to that table: not from another
service, not from a script, not from a console, not from `root`, not from a release nobody has
written yet. Removing it is a schema change — a migration, a diff, a review, and, because of §3.4, a
snapshot diff whose filename says the gate changed. This is also why our procedural code declines to
pre-empt the `CHECK` (§2.3, R-4): keeping the named constraint as the refusing mechanism is worth
more than the convenience of raising early.

**The honest boundary of that argument.** A `CHECK` constrains *one row*. Almost every interesting
safety condition is about *other rows* — an obligation over here, an incident over there — and no
`CHECK` can see them. That is the gap the whole idiom exists to close: **PROJECT** carries the
cross-row fact onto the row as a scalar so that a plain `CHECK` can reach it, and **PIN** stops the
answer from being falsified after the fact by rows that arrive later. Each part is unremarkable
alone. Together they make a [diachronic](GLOSSARY.md#diachronic) condition — a condition about how
the world got here, not merely how it is now — enforceable by ordinary declarative machinery, with
the finality of ordinary declarative machinery.

**And what it still does not claim.** It does not claim a determined organisation cannot route
around the system entirely, by opening a different subject or by not using it at all
(`spec/invariants/I14-minimal-refusal.md:96-97`). It claims the refusal is total over *writers to
this table*, and that it is explained well enough — an irreducible reason set
([MUS](GLOSSARY.md#mus)), and the [nearest admissible alternative](GLOSSARY.md#naa) where one is
computable — to remove the most common and most reasonable motive for routing around it. On the
measured refusal that reason set had cardinality 1, naming the one open obligation
[src: evidence/gate-refusal/proof-20260810T054407Z.json#refusal.refusal_ledger.mus_cardinality].

---

## 5. Where this goes next

That is the mechanism: a number the database writes, a pin that stops the past being edited, and a
constraint that refuses. **And this is what one request does with it** —
[chapter 2 · the request path and the four beats](02-the-request-path.md) takes one HTTP call against
the live deployment and shows each beat, including the one where the counter is forged out of band
and the database catches it. Where the obligations came from in the first place is
[chapter 3](03-memory-and-blame.md); what is *not* built, in full, is
[chapter 5](05-what-is-not-built.md).

---

*Citation convention, borrowed from [`docs/HONESTY.md`](../HONESTY.md): `[src: path#pointer]` gives
the artefact and the field; `cases[id=CF-63]` selects the array element whose `id` is `CF-63`.
Digits inside `code spans` are names, not measurements. Nothing here was re-measured in this
session — every number is quoted from a committed artefact and carries the pointer to it.*
