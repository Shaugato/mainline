<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MAINLINE — the architecture, from the front door

This page is the way in. The first section takes about a minute and needs no knowledge of
databases. Everything after it goes one layer deeper, ending in file-and-line evidence.

---

## Sixty seconds

**The scenario below is invented.** Kestrel Resources is fictional, Marrindal is fictional,
`INC-2013-044` never happened. The mechanism is real; the inputs are authored
(`docs/submission/MUST-NOT-CLAIM.md` §3).

An engineer at a gas plant wants to raise the high-pressure alarm setpoint on a compressor
from 135 back to 150. It is a routine request. It is also defensible: the plant has run clean
for years, and the lower setpoint trips nuisance alarms that people have started ignoring.

Before the job can be authorised, the system asks where that number came from. A seal fire
burned two contractors on 2013-06-12. On 2013-08-04 an engineer lowered the alarm because of
it, and saved one line with the change: *"Lowered 150 → 135 after seal fire INC-2013-044 — two
contractors burned."* That engineer left the company on 2021-07-16.

The authorisation is then **refused**. Not flagged, not warned about, not shown in a sidebar
that a busy person can scroll past. The database will not record the authorisation at all,
until a named, qualified person writes down and signs what they intend to do about a
thirteen-year-old fire that burned two people.

Nobody on shift in 2026 knew that number had a body behind it. The only person who did know
left five years ago, and what they left behind was one line of text in a system nobody reads.

That is the entire product. The rest of this document is how it is built and how you can
check that it is real.

*(Every date, label and setpoint above is transcribed from
`verticals/mainline/fixtures/corpus/answer-key/spine.json` — `dates` and `revisions`. The same
scenario opens [`README.md`](../README.md). The refusal it describes runs against a live
database and is transcribed in `evidence/gate-refusal/`.)*

---

## Why no existing system does this

Every permit-to-work system that ships today asks the same shape of question before it lets
work start: **is the world all right at this moment?** Are the isolations in place. Is the gas
test still in date. Is the welder's ticket valid. Those are good questions and this system
asks them too.

But they are all questions about the present. Judged-on-how-things-are-now is called
**synchronic**, and every one of those checks passes cleanly in the scenario above, because
nothing about the plant today is wrong. The compressor is fine. The paperwork is fine. The
request is reasonable.

The question that fails is a different kind: **how did this rule get to be the way it is?**
Judged-on-how-it-got-here is called **diachronic**. It is a question about the past of the
rule rather than the state of the plant, and no shipping permit system can express it —
because to express it you need the rule to remember what caused it to be written, and to
still be remembering it five years after the author has gone.

The word for that is memory, and the difficulty is not storing it. Storing it is easy, and
plenty of systems store incident reports. The difficulty is making the memory **binding**: a
memory that a person under schedule pressure at 04:00 cannot dismiss, and that an application
under maintenance cannot forget to consult.

---

## Where the refusal actually lives

The usual place to put a rule like this is application code — a service that checks the
history and returns an error. That is where it would be easiest to write, and it is the wrong
place, for a reason that has nothing to do with code quality: **anything that can be reached
by another writer is not enforced.** A migration script, an admin console, a data fix, a
second service written next year by someone who never read this document — each of those
writes to the same tables, and each of them bypasses a rule that lives in one service.

So the refusal lives in the database, as three ordinary database objects that no writer can
go around:

* a `CHECK` constraint — `gate_closed_when_issued`, at
  `verticals/mainline/db/migrations/0050_permit.sql:114`. It says, in effect: a permit may not
  be in the `merged` state while its count of unsettled
  [obligations](architecture/GLOSSARY.md#obligation) — things this job must settle before work
  starts — is above zero.
* a trigger — `permit_merge_gate`, at
  `verticals/mainline/db/migrations/0130_trg_permit_merge_gate.sql:38`. It recomputes that
  count from the underlying rows immediately before the constraint is evaluated, so a writer
  who simply sets the count to zero does not get their write through.
* a procedure — `mainline.fn_permit_merge_gate()`, at
  `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:44`. It re-derives the count
  a second time and refuses when its own derivation disagrees with the stored value.

When the constraint refuses, the database returns `23514` and the name of the constraint that
did it. When the procedure refuses, it returns `P0001`. Those five-character codes are called
SQLSTATEs, and this document treats them as the evidence rather than treating any English
message as the evidence, because the code and the constraint name come from the database and
the message could come from anywhere.

Chapter 01 is the full mechanism. Every term used above is defined in the
[glossary](architecture/GLOSSARY.md).

---

## A note for anyone who went looking for this file before

**There is no pre-existing `ARCHITECTURE.md` in this repository, and this page is not a
summary of one.** `README.md:443` says where it went, in the repository's own words:

> Design corpus: `ARCHITECTURE.md` and `BUILD_PLAN.md` live in a companion research
> repository, not this one.

That is accurate and it is confirmed here: a search of the whole tree for any file whose name
contains `architect` returns nothing but the plan this wave was written from. So if a
reference sent you looking for a design document that is not here, this is why.

What *is* here is the layer that matters most for checking a claim — a precise, dense,
already-written corpus that this page and its five chapters link down into rather than
replace. Nothing in it was edited by this wave. The main entries are
[`spec/TRAPPOINT-SPEC.md`](../spec/TRAPPOINT-SPEC.md) and the sixteen invariants beside it,
[`docs/deploy/gate-run-contract.md`](deploy/gate-run-contract.md),
[`docs/demo/LIVE-SEMANTICS.md`](demo/LIVE-SEMANTICS.md),
[`docs/HONESTY.md`](HONESTY.md), [`docs/TOOL-USAGE.md`](TOOL-USAGE.md) and
[`docs/CI-STATE.md`](CI-STATE.md).

---

## The five chapters, in order

Read them in this order. Each one hands off to the next at a named sentence.

1. [**01 — The mechanism**](architecture/01-the-mechanism.md) · PROJECT, PIN, REFUSE: one idea
   in three parts, and why it is in the database rather than in a service.
2. [**02 — The request path**](architecture/02-the-request-path.md) · what one HTTP request
   does end to end, in four beats, including the beat that forges a counter to prove the
   [gate](architecture/GLOSSARY.md#gate) does not trust its own arithmetic.
3. [**03 — Memory and blame**](architecture/03-memory-and-blame.md) · where the obligation came
   from: an incident, a clause, a blame edge, and a walk over ancestry.
4. [**04 — The map**](architecture/04-the-map.md) · what lives where in the tree, and the one
   boundary that is simultaneously a layer, a licence and a liability.
5. [**05 — What is not built**](architecture/05-what-is-not-built.md) · the enumerated gaps,
   with numbers, kept on the page on purpose.

Alongside them: the [**glossary**](architecture/GLOSSARY.md) — twenty-four terms, each glossed
in plain language before it is given a table or a route.

---

## The component map

Three layers, extending the version in `README.md`. Every box below is a directory or a file
that exists in this tree.

```
verticals/mainline/            ← THE PRODUCT                LicenseRef-FSL-1.1-ALv2
  apps/console/                  the screen an operator uses (index.html)
  apps/demo-api/                 the HTTP surface (src/mainline_demo_api/app.py)
  apps/steward/                  the back-office worker
  packages/mainline-domain/      the permit, clause and incident model
  packages/mainline-gate-svc/    the caller that drives the gate and reads the refusal
  packages/mainline-recall-agent/  what looks up the past that a new job resembles
  db/migrations/                 271 .sql files — where the gate physically is
        │
        │  rendered from and validated against
        ▼
packages/trappoint-*           ← THE SUBSTRATE              Apache-2.0
  trappoint-sql/templates/       the SQL the gate is rendered from (0115_fn_merge_gate.sql.j2)
  trappoint-migrate/             applies migrations in order
  trappoint-conformance/         the case list that is the only meaning of "compliant"
  trappoint-verify/              the offline bundle checker, runs with no network
  trappoint-jcs/                 RFC 8785 canonical JSON, so two machines hash alike
  spec/ (at the repo root)       TRAPPOINT-SPEC.md and invariants I01–I16
        │
        │  enforced by
        ▼
CockroachDB v26.2               ← THE MEMORY LAYER
  four objects, all under verticals/mainline/db/migrations/ :
  CHECK    gate_closed_when_issued        0050_permit.sql:114
  TRIGGER  permit_merge_gate              0130_trg_permit_merge_gate.sql:38
  FUNCTION mainline.fn_permit_merge_gate  0115_fn_permit_merge_gate.sql:44
  FK       (subject_id, gate_epoch) ON UPDATE RESTRICT  0071a_epoch_pin_permit.sql

  The refusal happens HERE. Not in application code, and not in a screen.
```

The migration count re-derives with `ls verticals/mainline/db/migrations/*.sql | wc -l`. The
substrate knows nothing about safety permits: the words *permit* and *incident* belong to the
vertical, not to TRAPPOINT, which is what makes the Apache-2.0 half genuinely forkable.

Three directories sit beside that stack rather than inside it, and chapter 04 places them:
`infra/` (OpenTofu modules — `cost-guard`, `demo-api`, `demo-site`, `evidence-store`),
`evidence/` (transcripts and captured tool evidence) and `qa/` (the counted ratchets and the
command that re-derives each number).

---

## Scope, stated before you find it yourself

This is a hackathon build and it is pre-alpha. The scope below is not a disclaimer at the
bottom of the page; it is the reason the rest is worth believing. Chapter 05 enumerates all of
it with numbers and file references — [**what is not built**](architecture/05-what-is-not-built.md).

The five worth knowing before you read anything else:

* **Agent Skills is designed, not exercised.** The two skills under `skills/` are written and
  shaped for upstream; they have not been run as part of a demonstrated path.
* **Bedrock executes in this repository and not in the demo request path.** Real model calls
  were made and recorded, with AWS request ids. The live demo does not make one.
* **The change-request use case is missing two of its steps, and says so in its own answer.**
  It returns `admission_beat: null` and `kernel_procedure_beat: null`, each with a written
  reason, rather than leaving the fields out (`docs/demo/VERDICT-TWO-CASES.md:29`). Chapter 02
  walks the steps — the repository calls them *beats*.
* **Custody is 9 passed, 0 failed, 7 not checked, of 16**
  [src: qa/test-state.json#external_checks.custody_bundle_verification.counts]. Seven
  cryptographic checks are unwritten, and the offline verifier exits non-zero saying so.
* **21 of 30 MAINLINE invariants are pending.**

Every one of those is a place where the shortest route to a better-looking submission was to
delete the question instead of answering it.

---

## One gap in this page's own quality gate

This repository has a docs ratchet: a list of pages that automated sweeps read line by line
and fail on when a number in the prose disagrees with the number in the artefact. The list is
the `LIVE_DOCS` tuple at `tests/deploy/test_cost_model.py:96-127`, widened once by
`SWEPT_DOCS` at `tests/deploy/test_docs_are_true.py:119-123`, and the sweeps that run over it
live in `tests/deploy/test_docs_are_true.py`.

**This page and its five chapters are not in that list, and this wave did not add them.** The
tuple belongs to another owner, and editing a test file to bring new prose under a gate is
exactly the change most likely to disturb a green suite for a cosmetic reason. So the honest
statement is that these pages are checked by review and by their citations, and not yet by a
machine.

The addition that would close it is one line per page in either tuple — `"docs/ARCHITECTURE.md"`
in `LIVE_DOCS`, or in `SWEPT_DOCS` following the precedent that file set for itself on
2026-08-15. Expect it to go red the first time: a wider aperture that produces no reds was not
worth widening, which is the reasoning `tests/deploy/test_cost_model.py:89-90` already records
in its own words.

---

## Checking this without trusting us

[`VERIFY.md`](../VERIFY.md) is the three tiers, ordered by how much you have to take on faith.
Tier 2 reproduces the refusal described at the top of this page on your own laptop, with no
account of ours and no model call.

Two artefacts are worth opening directly: [`evidence/gate-refusal/`](../evidence/gate-refusal/),
which holds transcripts of what one cluster did at one instant — SQLSTATE, constraint name,
the projected count either side of a single insert, and the caveats the run could not honestly
avoid; and [`docs/HONESTY.md`](HONESTY.md), which lists the claims that are *not* proven, by
name, rather than leaving them out.
