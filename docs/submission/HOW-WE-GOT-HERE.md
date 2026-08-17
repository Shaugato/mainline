<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# HOW WE GOT HERE

**What this page is.** The story of the project, told as a sequence of things we believed,
tested, and were wrong about — because that is what actually happened, and because a list of
things that worked is the least informative document a team can write. Every claim on this page
names the file that holds it, so you can check any sentence without taking our word for it.

**Who it is for.** The first section is for anyone. The rest gets more technical as it goes, and
each term is explained the first time it is used.

---

## Sixty seconds

A maintenance procedure says a compressor may be run up to `135`. The manufacturer's plate on the
machine says `150`. An engineer notices the gap and raises the number back to `150`. This is
defensible. It is also, on every permit system on the market, approvable: the form is complete,
the signatures are current, and the number now agrees with the manufacturer.

The number was lowered years ago, after a fire, by an engineer who wrote down why and then left
the company. The document survived. The reason did not. It sits in an incident report nobody
opens, and the people who would have said *wait* have moved on.

That is the failure this project is about, and it is not negligence. Nothing in the systems that
run this work was ever built to carry *why a rule says what it says*. So an organisation's memory
of an event decays to nothing on the day its author resigns.

MAINLINE makes that memory a condition of the work rather than a note beside it. Before a job can
be marked complete, the database itself looks at the history the rule came from and **refuses the
write** until a named person has signed an answer to what it found. Not a warning banner shown
next to an Approve button. A refusal, from the database, carrying the name of the rule that
refused.

> *The compressor example is authored.* Every incident, site, rule and permit in this
> demonstration was written for it. The seeded incident says so in its own text: *"No real
> incident, no real site, no real fatality: this narrative was written for the MAINLINE
> demonstration and describes nobody"*
> (`verticals/mainline/db/seeds/demo/demo_world.sql:276-278`). The mechanism is real; the inputs
> are designed.

---

## The words this page uses

Each of these is used later. None is used before this list.

- **permit-to-work** — the form a supervisor signs before a crew opens a live machine.
- **clause** — one numbered rule inside a procedure: *"isolate at zero and verify."*
- **blame ancestry** — the chain of events that caused a clause to say what it says, stored as
  database rows rather than as prose. The same idea as `git blame` on a line of source code:
  every line points at the change that last touched it.
- **synchronic** — checking the world as it is right now. *Is the gas test valid today? Is the
  signature present today?*
- **diachronic** — checking what a decision depends on and what has happened to those
  dependencies since. *Which rules does this job lean on, which events wrote those rules, and has
  anybody answered for them?*
- **obligation** — a debt the system raises against a decision. Somebody must answer it before
  the decision can complete.
- **disposition** — a named person's signed answer to one obligation.
- **projection** — a database trigger (code the database runs automatically on every write)
  copying a fact from other rows onto the row being written, taken from an authoritative table
  and never from whoever is doing the writing.
- **epoch** — a counter attached to a job that goes up every time a new obligation appears, so a
  job already marked complete cannot have a new question attached to it afterwards.
- **SQLSTATE** — the five-character code a database returns when a statement finishes. `00000`
  means it succeeded; `23514` means a `CHECK` constraint was violated; `P0001` means code inside
  the database deliberately raised an error; `42P01` means a table the statement named does not
  exist; `42501` means the user lacks a privilege.
- **negative control** — a test whose job is to go red when one specific thing goes wrong. A
  control nobody has ever made fail proves nothing, so this repository plants faults on purpose
  to check that its controls notice.
- **canonicalisation** — turning a record into one exact string of bytes, so that two programs
  processing the same data produce identical bytes and therefore identical hashes.

---

## Part one · three beliefs about where the check belongs

### We believed we could enforce this in the application. We could not.

The obvious build is a rule in the service that handles permits: before marking a permit
complete, look up the history, and stop if something is unanswered.

It does not hold, for a reason that has nothing to do with code quality. **An application rule is
a rule for the people who use that application.** A back-office correction made with a direct
database session does not go through it. A migration script does not go through it. A second
service written next year by somebody who did not read this one does not go through it. In an
industry where the interesting writes are precisely the unusual ones — the correction, the
retrofit, the emergency — a control that only covers the usual path covers the wrong set.

The correction is now normative in our own specification: *every gate condition expressible as a
predicate over columns of a single row MUST be declared as a `CHECK` constraint on that row's
table. It MUST NOT be enforced by procedural code alone* (`spec/TRAPPOINT-SPEC.md` §2.3, rule
**R-1**).

### We believed we could show the reason next to the decision. That is worth nothing.

The cheaper design is to retrieve the relevant incident and display it beside the Approve button.
It changes no schema, and it is worth nothing for the same reason.

**A document shown next to an Approve button is a nag, and a nag gets dismissed.** It is
dismissed under time pressure, by the fifth person that shift, and the dismissal leaves no record
anybody can be asked about later. Whether it was read is unrecorded and unenforceable.

### What survived: recall as a precondition, not a panel

The thing that cannot be routed around is a database constraint. So the recall of the history had
to stop being a panel beside the decision and become a **precondition of the state transition** —
the write that marks the job complete either satisfies the condition or does not happen.

That sentence is the whole project. Everything else in this repository is the machinery that
makes it true and the evidence that it is.

The machinery is three parts, normative in `spec/TRAPPOINT-SPEC.md` §2, each stated plainly and
then technically:

- **PROJECT** — the database, not the person filling in the form, records whether anything is
  still owed on this job. Technically: a trigger writes a **projection** onto a single ordinary
  column of the job's row, so that a constraint can read it. Where the authoritative source holds
  no row, the trigger refuses rather than defaulting to zero (rule **P-3**): *absence of evidence
  refuses; it never admits.*
- **PIN** — once a job is complete, nobody can attach a new question to it. Technically: the
  record of the completed transition carries a foreign key onto `(subject_id, gate_epoch)`, so
  attaching a late obligation stops being a policy violation and becomes a referential-integrity
  violation the database itself rejects (rule **N-4**).
- **REFUSE** — the refusal lives in the table, so it applies to every way of writing to that
  table. Technically: each independently nameable refusal gets its own named `CHECK`, **because
  the constraint name is the exhibit** (rule **R-2**). *"The merge was refused by
  `gate_closed_when_issued`"* and *"a counter was non-zero"* are materially different sentences.

What that looks like when it runs, read out of the committed artefact
`evidence/gate-refusal/proof-20260810T054407Z.json`, whose `verdict` is `PROVEN` with an empty
`caveats` list:

| # | attempted | outcome |
|---|---|---|
| 1 | read the permit and the obligation still open on it | `00000` |
| 2 | mark the permit complete — one open obligation, nobody has signed | `23514` `gate_closed_when_issued` |
| 3 | mark it complete again, having forced the projected counter to zero from another session | `P0001` `mainline.fn_permit_merge_gate` |
| 4 | mark it complete after a named person signs a disposition | `00000` |

Beat 3 is the one worth staring at. The counter the constraint reads was set to zero directly,
around the application. The `CHECK` in beat 2 is now satisfied. The write is refused anyway,
because the gate re-derives the count from the obligation rows and refuses on the disagreement
itself. And beat 4 matters equally: **a gate that always refuses is not safe, it is an
outage**, and an outage gets routed around inside a week.

*Depth on this argument, including the dated prior-art sweep behind it, is in
[`docs/story/05-why-ancestry.md`](../story/05-why-ancestry.md). This page states it in summary and
does not repeat it.*

---

## Part two · six things we believed about our own build, and measured wrong

These are build-era mistakes, each found by measurement, each with the control that caught it.
They are here because they are the honest answer to *how did you get here*, and because each one
changed how the rest of the project was built.

### 1. We believed that counting failures counts what is missing. It counts what got named first.

Our migration chain — the ordered set of files that builds the database schema — was halting. The
cause was **tables that some file referenced and no file created**. To count them, we counted the
failures: every failing migration reported SQLSTATE `42P01`, *relation does not exist*, and each
one named a relation. The census read **five**.

The truth was **seven**
(`evidence/producers/producer-census-before.json#before.absent_relations`, a list of seven names,
re-derived for this page).

The gap is a property of the database. **CockroachDB reports the *first* absent relation in a
statement.** `mainline_meas.person_measure_policy` was joined alongside `mainline_meas.standing`
in two views, and `standing` is named first in both — so `person_measure_policy` never appeared in
any SQLSTATE, anywhere. A census of error codes could not have found it
(`docs/release/chain-268.md` §2).

Worse, the number was stable under the wrong fix. Creating `standing` alone does not make the
`42P01` go away; it **moves one file along**, because `standing.policy_id` is `NOT NULL` with a
foreign key into the table nobody created. The failure count is identical before and after a fix
that is wrong, so the failure count could never have told anybody the fix was wrong
(`docs/deploy/unproduced-tables.md` §1).

**The correction is a different question.** Not *which tables did somebody notice were missing*,
but *which relations does any statement in this tree name, and does a `CREATE TABLE` for each one
exist anywhere*. That question is answerable by a program with no cluster at all, and it is now a
lint rule that runs over the whole tree
(`packages/trappoint-migrate/src/trappoint_migrate/producers.py`). The chain now applies `271` of
`271` files.

**Why it is on this page:** it is the cleanest example of the pattern this project keeps finding.
A number that looks like a measurement is often a measurement of the reporting channel.

### 2. We believed the database's own privilege function tells the truth. On this version it does not.

We wrote a guard to check that database roles hold the grants we think they hold. The first draft
asked `has_function_privilege(role, oid, 'EXECUTE')`.

Following our own rule that a control nobody has made fail proves nothing, we planted a fault: on
a scratch database, we revoked `EXECUTE` and expected the check to go red. It did not. The
behavioural truth on the same database, in the same session, was

```
CALL as probe: REFUSED 42501 user w_rg_probe does not have EXECUTE privilege on procedure merge_permit
```

and `has_function_privilege` answered `true` anyway — for that role, for `root`, for `admin`, for
`public`, for everybody. **A check built on it cannot fail, and a check that cannot fail is
decoration.** We replaced it with a `SHOW GRANTS` read plus explicit expansion of role membership,
which costs work the built-in would have done for free, and which can go red
(`docs/regression/GUARD.md`, section *Two things this guard found on its first run*).

`has_table_privilege` was put through the identical control on the same database and tracks
behaviour exactly, which is why table privileges are still decided by it. That is the honest shape
of the finding: one function, measured, not a complaint about the platform.

*This and the other measured platform findings are catalogued as feedback to CockroachDB rather
than argued here.*

### 3. We believed a lane that exits `0` has checked something. A skip and a pass are the same colour of nothing.

Our most important continuous-integration job runs the proof that the database refuses the merge.
The test skips when it cannot reach a database, which is correct — *"there was no database"* is
not evidence that the gate admitted anything. But **pytest exits `0` when every test skips**, and
the job read the exit code.

Measured with every database address pointed at a closed port: `15 skipped in 21.47s`, exit `0`,
lane green (`docs/ci/anti-vacuity.md` §2.1). The product's central claim was reported as held on a
run that proved nothing.

The census that found it asks one question of every automated job: *can this lane prove it is able
to fail?* **Seven of eighteen jobs carry a standing negative control after that work, against
three before it — and the table names the eight that still have none**
(`docs/ci/anti-vacuity.md:55`). Publishing the eight is the part that matters; a census that only
lists its wins is the artefact it was written to replace.

### 4. We believed a verifier that prints nine ticks looked at sixteen things.

`trappoint-verify` is the tool a stranger uses to check our evidence without our help. Sixteen
checks are specified. A real bundle of evidence will not always support all sixteen — a bundle
with one checkpoint has no consecutive pair to compare — and in that situation the comfortable
option is to print the ticks you have and say nothing.

That is the default behaviour of almost every verification tool ever shipped, because **a skipped
check looks like a passing check to everything downstream**: to an exit code, to a screenshot, to
a person reading a report at the end of a long day.

So a skip is printed in the same bold red as a failure, from the same style constant; any report
containing one opens with a `NOT CHECKED` banner naming every skipped check before a single pass
is printed; and there is a dedicated exit code `2` meaning *nothing failed, and something was not
looked at* (`docs/adr/0046-verifier-skip-is-loud.md`). Run over our own committed reference
bundle, the tool exits `2` and the headline is `9 passed · 0 failed · 7 not checked` rather than a
clean tick.

We chose the worse-looking number on purpose. **A tick obtainable by not looking is worth
nothing.**

### 5. We believed a database sequence could number a tamper-evident log. It makes the check vacuous.

Our evidence log claims that a gap in its numbering is a sign of tampering. Whether that sentence
is useful or a lie depends entirely on how the numbers are produced.

`nextval()` — the standard way to number rows — is deliberately non-transactional: increments
survive a rollback, because that is what makes a sequence fast. A log numbered that way has
*legitimate* gaps, one per rolled-back transaction. A gap would then be equally consistent with an
ordinary failed insert and with a deleted record, and **a check that cannot distinguish those is
not a check** (`docs/adr/0045-cas-sequencing-not-sequences.md`).

The position is instead derived inside the appending transaction, and two concurrent writers
collide. The collision arrives as SQLSTATE `23505`, which is also how the database says *"this was
already recorded"* and *"a settled hash was rewritten"* — facts that must never be retried away.
So the retry matches on the **constraint name**, not the SQLSTATE, and a `23505` whose constraint
cannot be named is not retried at all: a retry keyed on an absent name is a blanket retry in
disguise. Measured with sixteen concurrent writers and no coordination: `160` records, positions
dense `0..159`, `317` attempts, none exhausted.

The tempting shortcut — retry on SQLSTATE `23505` — is one line shorter and turns every real
refusal into a silent success.

### 6. We believed a JSON number is a JSON number.

Our evidence scheme reduces to one sentence: *a stranger, holding only the record and an
open-source verifier, reproduces the bytes we hashed.* Producing those bytes is
**canonicalisation**, and the standard for it (RFC 8785) requires numbers to be written exactly as
JavaScript writes them.

Every other runtime disagrees. JavaScript writes `1e-5` as `0.00001`; Python and Go write
`1e-05`. JavaScript writes `-0.0` as `0`; Python writes `-0.0`. A canonicaliser that reaches for
its own language's number formatter is wrong on those cases, and **the failure is silent** — the
bytes hash, the record commits, and the disagreement surfaces years later when somebody else's
verifier reports a mismatch, which reads in a report as *tampering*
(`docs/adr/0042-float-ban-in-evidentiary-payloads.md`).

We implement the standard in full and then refuse to use the risky part: no binary floating-point
number may enter an evidentiary payload at all, at any depth. A setpoint is a decimal string on a
nameplate. A severity is an integer `1`–`5`. A pressure is an integer in its smallest unit. The
set of fields that genuinely needed a float was empty before we looked.

**The failure mode we removed is not "our numbers might be slightly wrong". It is our own
tamper-evidence scheme manufacturing a false accusation against us.**

---

## Part three · the method these mistakes produced

Six mistakes with one shape: **something agreed with something else, and nothing was holding them
in agreement.** The tests agreed with the code because both drew on the same constant. The green
lane agreed with the claim because both were silent. The privilege check agreed with the grant
because it agreed with everything.

Three practices came out of that, and they now bind every piece of work in this repository.

**Prove agreement by executing something.** Reading two files and believing they match is how
every one of these survived review. When we finally went looking for duplicated truth
systematically, the rule was written down first: *a pair that happens to agree today, with nothing
holding it in agreement, is a finding* — reported with its own severity, and with a column naming
the mechanism that would scream if they stopped agreeing, or the word `NOTHING`
(`docs/diagnosis/divergence-census-plan.md` §1).

**Plant the fault before you trust the control.** Every control in this repository is expected to
have been made to fail on purpose at least once. The ones that have not are listed as unproven
rather than counted as passes (`docs/regression/GUARD.md`, section *What could not be falsified*).

**Publish the numbers that got worse.** `docs/HONESTY.md` carries an inline reference on every
quantity, and a test reads that page, follows every reference, and fails the build when a number
and its source disagree. One of its rules runs the other way from the rest: it fails when evidence
*appears* that the page does not mention — because the failure the page actually suffered was a
number that had been true for a day before anybody printed it.

---

## Why this is the solution we needed

Every permit-to-work system on the market is **synchronic**: it asks whether today's paperwork
satisfies today's wording. None of them can express *why* a rule says what it says, so the memory
of the incident that produced the rule decays to nothing the day its author resigns.

We tried to fix that in application code and could not, because application code is routed around.
We tried to fix it with a document displayed beside an Approve button and could not, because a nag
gets dismissed and leaves no record.

**The thing that cannot be routed around is a database constraint. So recall had to become a
precondition of the state transition rather than a panel beside it.**

That is why this is the solution we needed, and it is the sentence the whole project rests on.

---

## What this page does not claim

Stated here in the same words used everywhere else in this repository, because these scopings are
why the rest is believable.

- **The CockroachDB Agent Skill that packages this pattern is `DESIGNED`, not `EXERCISED`.** The
  files are on disk; no captured run of them exists under `evidence/`.
- **Amazon Bedrock runs in this repository and is not in the demo's request path.** Both halves of
  that sentence, always. The four beats a judge can trigger are SQL against CockroachDB, with no
  model call.
- **The second use case, the change request, has no admission beat.** Its gate refuses — `23514`
  `cr_gate_closed_when_merged`, then `P0001` `fn_cr_merge_gate` — and its admission beat is
  declared rather than run.
- **The corpus is authored.** No real incident, no real site, no real fatality.
- **The prior-art finding is a dated sweep** by one reviewer over three named products on
  `2026-08-02`, not a survey of the field.

---

## Where to read further

| you want | read |
|---|---|
| the sixty-second version and a map of the whole story | [`docs/story/ORIGIN.md`](../story/ORIGIN.md) |
| how the idea was searched for and chosen, and the audit that found against its own commissioner | [`docs/story/01-the-search.md`](../story/01-the-search.md), [`02-the-choice.md`](../story/02-the-choice.md), [`03-the-audit.md`](../story/03-the-audit.md) |
| the three build mistakes at full depth, with the controls that caught them | [`docs/story/04-wrong-turns.md`](../story/04-wrong-turns.md) |
| the synchronic-versus-diachronic argument in full | [`docs/story/05-why-ancestry.md`](../story/05-why-ancestry.md) |
| the mechanism, normatively | [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2 |
| what is not built, with the command that re-derives each gap | [`docs/HONESTY.md`](../HONESTY.md) |
| whether each automated job can prove it is able to fail | [`docs/ci/anti-vacuity.md`](../ci/anti-vacuity.md) |
| the guard that found the privilege stub | [`docs/regression/GUARD.md`](../regression/GUARD.md) |
| the decisions behind parts two-five and two-six | [`docs/adr/0042-float-ban-in-evidentiary-payloads.md`](../adr/0042-float-ban-in-evidentiary-payloads.md), [`0045-cas-sequencing-not-sequences.md`](../adr/0045-cas-sequencing-not-sequences.md), [`0046-verifier-skip-is-loud.md`](../adr/0046-verifier-skip-is-loud.md) |

<!-- word count: `python -c "print(len(open('docs/submission/HOW-WE-GOT-HERE.md',encoding='utf-8').read().split()))"` -->
