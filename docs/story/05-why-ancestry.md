<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Why ancestry

A number in a maintenance procedure reads `135`. The manufacturer's figure is `150`. An
engineer raises it back — technically correct, and every permit system we surveyed would
approve the job.

The number was lowered years ago, after a fire, by an author who wrote down why and then
left. The document survived. The reason did not. It sits in an incident report nobody opens,
and the people who would have said *wait* have moved on.

Almost every system that checks a rule checks one thing: does today's paperwork satisfy
today's wording? None can hold what makes the rule worth obeying — what happened, and what
the rule was written to prevent. So an organisation's memory of an event decays to nothing on
the day its author resigns. Not negligence: nothing in the system was built to carry it.

MAINLINE makes that memory a condition of the work. Before a job can be marked complete,
the database looks at the history the rule came from and refuses the write until a named
person has signed against what it found. Not a banner. A refusal.

*(The worked example above is authored: no real incident, no real site, no real fatality.)*

---

## Two words, and what they mean here

**Synchronic** means *checking the world as it is right now*. Isolation in place, gas test
valid, signature present, competency current. Every box is a fact about this moment, and the
check passes when all of them are true today.

**Diachronic** means *checking what a decision depends on and what happened to it*. Not the
state of the form, but the state of the history behind the form: which rules this job leans
on, which events wrote those rules, and whether anybody has answered for them.

Three more terms, because the rest of this page uses them.

- A **clause** is one numbered rule inside a procedure — *"isolate at zero and verify."*
- A **permit-to-work** is the form a supervisor signs before a crew opens a live machine.
- **Blame ancestry** is the chain of events that caused a clause to say what it says, held
  as database rows rather than as prose. In MAINLINE a clause version carries a pointer to
  the event that wrote it, the way a line of source code carries a `git blame` pointer to
  the commit that last touched it (`hackathon-research/research/05-architecture/commit-dag.md`).

Everything below is one claim: **the difference between gating on the present and gating on
the ancestry is a difference in kind, and it is the whole product.**

---

## The sweep, and a date on it

A prior-art search run on **2026-08-02** by an independent novelty reviewer looked for a
shipping permit or document-control gate conditioned on ancestry rather than on current
document state. It examined **Veeva QualityDocs, MasterControl and Enablon/Cority**, found
all of them synchronic, and **found none conditioned on ancestry**
(`hackathon-research/research/04-final/judge-novelty.md:146` — that is a separate research
repository held alongside this one, not a path inside this tree).

Read that as what it is: a dated finding by one reviewer over three named products. It is
**not** a claim that no such gate exists anywhere. The same reviewer docked other claims in
the same corpus for exactly that error — promoting a narrow truth to a universal — and the same
table records those docks in the rows beside this one.

---

## Where the difference bites

In a synchronic system, recall is a **panel**. The relevant incident is retrieved, shown
beside the decision, and the decision proceeds. Whether anyone read it is unrecorded and
unenforceable.

In MAINLINE the merge condition is evaluated over an ancestry, so recall stops being a panel
beside the decision and becomes a **precondition of the state transition**. Two terms carry
that:

- An **obligation** is a debt the system raises against a decision — someone must answer it
  before the decision can complete.
- A **disposition** is a named person's signed answer to one obligation.

*Merge* is borrowed from version control on purpose: the permit-to-work is treated as a
branch, and marking it complete is a merge. A permit may not reach `merged` while a recalled
precursor carries an obligation nobody has signed. That sentence is the product.

---

## The mechanism, in three steps

Normative in [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2, which states them
as one mechanism in three parts and says omitting any one makes the other two unsound. Each
gets a plain sentence and then the technical one.

**PROJECT.** *Plain:* the database, not the person filling in the form, writes down whether
anything is still owed on this job. *Technical:* a row-level trigger — code the database runs
automatically on every write to a table — copies a cross-row fact onto a **scalar column** of
the subject row (one ordinary column on one row, so a constraint can read it), derived from a
declared authority relation and **never** from the inserted row or from any table the
inserting role may write (§2.1, P-1 and P-2). That copying step is what this project calls a
**projection**. Where the authority source holds no row, the trigger refuses rather than
defaulting (P-3): *absence of evidence refuses; it never admits.*

**PIN.** *Plain:* once a job is complete, nobody can go back and attach a new question to it.
*Technical:* the record of a completed transition takes a composite foreign key — a
referential link the database itself enforces — onto `(subject_id, gate_epoch)`, declared
`ON UPDATE RESTRICT ON DELETE RESTRICT`, where the **epoch** is a counter on the subject that
increments every time a new obligation appears (§2.2, N-2 and N-3). The consequence is the
reason the pin exists: attaching an obligation to a completed subject stops being a policy
violation and becomes a referential-integrity violation (N-4). The writer is forced onto the
declared path — suspend the completed subject, open a child, clear its gate afresh.

**REFUSE.** *Plain:* the refusal is written into the table itself, so it applies to every way
of writing to that table. *Technical:* every gate condition expressible as a predicate over
one row's columns is declared as a named `CHECK` constraint on that table and must not be
enforced by procedural code alone, and each independently nameable refusal takes its own
`CHECK` with its own name, **because the constraint name is the exhibit** (§2.3, R-1 and
R-2). *"The merge was refused by `gate_closed_when_issued`"* and *"a counter was non-zero"*
are materially different sentences.

Being a constraint rather than application logic, it holds against a direct database session
and a back-office correction alike.

---

## What it looks like when it runs

A **SQLSTATE** is the five-character code a database returns when it refuses. `00000` means
the statement succeeded; `23514` means a `CHECK` constraint was violated; `P0001` means
procedural code inside the database raised.

Four beats, read out of the committed artefacts rather than re-derived here — the deployed
origin's run in [`evidence/deploy/live-gate-run.json`](../../evidence/deploy/live-gate-run.json)
and the local proof in
[`evidence/gate-refusal/proof-20260810T054407Z.json`](../../evidence/gate-refusal/proof-20260810T054407Z.json),
whose `verdict` is `PROVEN` with `caveats []`:

| # | what is attempted | outcome |
|---|---|---|
| 1 | read the permit and the obligation still open on it | `00000` |
| 2 | merge the permit — one open obligation, no signed disposition | `23514` `gate_closed_when_issued` |
| 3 | merge again with the projected counter forced to zero out of band | `P0001` `mainline.fn_permit_merge_gate` |
| 4 | merge after a named person signs a disposition | `00000` |

The obligation refused in beat 2 carries `origin: blame_ancestry` and `severity: 4` in that
artefact's own fields, and it traces to a seeded event whose title reads *"SYNTHETIC — Stored
energy release during intrusive work"* and whose narrative column ends *"No real incident, no
real site, no real fatality: this narrative was written for the MAINLINE demonstration and
describes nobody"* (`verticals/mainline/db/seeds/demo/demo_world.sql:276-278`).

---

## Why a refusal and not a warning

The obvious cheaper design is to show the incident next to the Approve button. It is cheaper
because it changes no schema, and it is worth nothing for the same reason.

**A document shown next to an Approve button is a UI nag, and a UI nag gets dismissed.** It
is dismissed under time pressure, by the fifth person that shift, and the dismissal leaves no
record anyone can be asked about. An invariant does not get dismissed. There is no path
around it — not a different client, not a direct SQL session, not a well-meant correction by
someone with more privilege than the crew.

That is why this had to live in the database and not in an application. An application rule
is a rule for the people who use that application.

---

## The counter the gate does not trust

Beat 3 is the claim under attack. The projected counter — the scalar column PROJECT writes —
was forced to zero *out of band*: written directly by another session, around the path the
application uses. So the `CHECK` constraint of beat 2 is now *satisfied*:
`open_blocking` really does read zero. The merge is refused anyway, because the gate
**re-derives** the count from the obligation rows and refuses on the disagreement itself
(`counter_forced_to 0`, `open_blocking_derived 1` —
[`verticals/mainline/demo/USE-CASES.md:255-267`](../../verticals/mainline/demo/USE-CASES.md)).

The corpus's own sentence for this, and the strongest one written about this product:

> **An attacker who owns the counter does not own the gate.**

Two limits belong in the same breath, because the sentence is worth less without them.

**It is scoped to this counter and this gate.** Nothing here is tamper-*proof*. A cluster
administrator can drop a constraint, and the answer to that is tamper-*evidence* — an
attested record that it happened — not prevention.

**And a gate that always refuses is broken, not safe.** That is what beat 4 is for. The same
history is admitted, `00000`, once a named person signs a disposition against it. A control
that cannot be satisfied is not a control; it is an outage, and it gets routed around within
a week. The mechanism has to be able to say yes, and the record of the yes — who, when,
against which event — is the artefact that makes the refusal mean something.

One further honesty note the artefact carries rather than hides: beat 3's refusal reports
`naa: null` with `naa_reason: not_computable`. A *nearest admissible answer* is the smallest
change that would make the write acceptable; for this class the system reports that it cannot
compute one instead of manufacturing a plausible number.

---

## What this argument does not claim

- **The corpus is authored.** Every clause, procedure, event, permit and site in the demo was
  written for this repository. The mechanism is real; the inputs are designed.
- **The competitor finding is a dated sweep**, by one reviewer, over three named products, on
  2026-08-02. Not a survey of the field.
- **The second use case has no admission beat.** The change-request gate refuses
  (`23514 cr_gate_closed_when_merged`, then `P0001 fn_cr_merge_gate`) and its admission beat
  is declared rather than run. It is reported that way everywhere it appears.
- **No model is called while a judge is looking.** The four beats above are SQL against
  CockroachDB. Amazon Bedrock is exercised in this repository and is **not** in the demo's
  request path.
- **The CockroachDB Agent Skill that packages this pattern is `DESIGNED`**, not `EXERCISED` —
  the files are on disk and no captured run of them exists under `evidence/`.

The distinction on this page is stated in full here and nowhere else. Every other document in
`docs/story/` gives it two sentences and links back.

<!-- word count: `python -c "import sys;print(len(open('docs/story/05-why-ancestry.md',encoding='utf-8').read().split()))"` -->
</content>
</invoke>
