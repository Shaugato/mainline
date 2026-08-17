<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# ORIGIN — why MAINLINE exists

An engineer at a gas processing plant opens a change form. A compressor's high-temperature
alarm is set to trip at `135`. The manufacturer's manual says `150`. They propose putting it
back to `150`.

Everything about that is defensible. The number they are moving to is the manufacturer's own.
The equipment register agrees with them. Every permit-and-change system we surveyed would
let it through, because every one of them asks the same question — *does the paperwork in
front of me satisfy today's rules?* It does.

None of them asks why the number was `135`.

It was `135` because a seal fire burned two contractors on `2013-06-12`, and somebody lowered
the alarm because of it on `2013-08-04` and wrote the reason down when they did. That person
left the company on `2021-07-16`. Everyone who was in the room has moved on. The paperwork is clean, the rule survives as a number with nothing
attached to it, and the number is about to be moved back by someone who has never heard of
the fire.

MAINLINE is a database that keeps the reason. It holds the chain from the fire, to the rule
the fire wrote, to the job about to be signed — as rows, not as a paragraph in a document
nobody opens. When a job is raised against a rule that some past event wrote, and nobody has
answered for that event, **the database refuses to let the job through.** Not a warning
banner. Not a red box beside an Approve button. The write does not land — not for the
application, not for an administrator at a command line, not for a back-office correction
script. A warning gets dismissed. A refusal has to be answered.

Answering it means a named person signing a specific reply to a specific question, rather
than ticking "N/A". Once that signature exists, the same job goes through. A gate that
always refuses is broken, not safe, so the record has to show both.

**The compressor story is a designed worked example.** `INC-2013-044` never happened: no
real incident, no real site, no real fatality, and the rule, the fire and the identifier
were written for this project ([`docs/HONESTY.md`](../HONESTY.md)). The *inputs* are
authored. The refusal is not — it happens, it is recorded, and the record is in this
repository for a stranger to open.

## What it actually is

Five words this project uses constantly, in plain language. A **permit-to-work** is the form
a supervisor signs before a crew opens a live machine. A **clause** is one numbered rule
inside a procedure — *"isolate at zero and verify"*. **Blame ancestry** is the chain of
events that caused a rule to say what it says, held as database rows rather than as prose.
An **obligation** is a debt the system raised against a decision: someone must answer it
before the decision can complete, and that answer is a **disposition** — one named person's
signed reply to one obligation. Every term this corpus uses is glossed in
[`GLOSSARY.md`](GLOSSARY.md), which the other story files are written against.

The refusal is three moves, normative in [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2:

- **PROJECT** — a trigger (a rule the database runs itself on every write) copies a
  cross-row fact onto a plain column of the row being written, derived from an authoritative
  table and never from whoever is writing.
- **PIN** — a completed decision takes a composite foreign key onto `(subject_id,
  gate_epoch)`. The **epoch** is a counter that increments whenever a new obligation appears,
  so attaching an obligation to an already-completed decision is not refused by policy; it is
  not expressible.
- **REFUSE** — a named `CHECK` constraint over that plain column refuses the write. For every
  writer. Ours included.

A **SQLSTATE** is the five-character code a database returns when it refuses. Two carry this
product: `23514` is a violated `CHECK` constraint, `P0001` is a trigger raising an error
itself. [`evidence/deploy/live-gate-run.json`](../../evidence/deploy/live-gate-run.json)
records four beats answered by the public Lambda Function URL over CockroachDB Cloud —
`00000`, then `23514 gate_closed_when_issued`, then `P0001 mainline.fn_permit_merge_gate`,
then `00000` once a disposition is signed — at verdict `PROVEN`, inside one `SERIALIZABLE`
transaction ending in `ROLLBACK`, with `persisted false`, so asking the question leaves
nothing behind for the next reader.

The third beat is the one worth understanding. Before it runs, the projected counter is
forced to zero out of band: the number the constraint reads is made to say *nothing is owed*.
The gate refuses anyway, because it re-derives the count instead of trusting the column
handed to it. [`verticals/mainline/demo/USE-CASES.md`](../../verticals/mainline/demo/USE-CASES.md)
puts it in one line — *an attacker who owns the counter does not own the gate.*

## The map — where the rest of the story is

| file | what you get there |
|---|---|
| [`01-the-search.md`](01-the-search.md) | Eighteen domains scanned and twelve problems tested against the products that already exist — and the six ideas that died, each with the reason it died. |
| [`02-the-choice.md`](02-the-choice.md) | Five finalists, three judges reading under different lenses, the score table, the written dissent, and why this one won on breadth rather than by a distance. |
| [`03-the-audit.md`](03-the-audit.md) | An auditor commissioned to attack the decision, which found against the person who commissioned it — and upheld the outcome anyway. |
| [`04-wrong-turns.md`](04-wrong-turns.md) | Three things we got wrong while building, each named with the control that caught it rather than with the lesson we drew. |
| [`05-why-ancestry.md`](05-why-ancestry.md) | The idea underneath all of it, at full depth: why checking the present is not enough, and what the alternative costs. |

## Checking the present, and checking the past

Every permit and document-control system we surveyed is **synchronic** — it checks the
world as it is right now: isolation in place, gas test valid, signature present. MAINLINE is
**diachronic** — it checks what a decision depends on and what happened to it — and that
argument, with the dated prior-art sweep behind it, is stated at full depth in
[`05-why-ancestry.md`](05-why-ancestry.md), which owns it.

## Scope — three limits, stated here rather than found later

**1 · CockroachDB Agent Skills is `DESIGNED`, not `EXERCISED`.** Two skills are on disk and
each ships an executable assertion script a reader can run. No run of either is captured
under `evidence/`, so the census records them in its own words as *"shipped and not
evidenced"* ([`evidence/tool-usage/crdb-features.json`](../../evidence/tool-usage/crdb-features.json),
row `crdb_agent_skills`). That file also fixes what the two words mean: `EXERCISED` is *"it
ran, and a committed artefact or a check in this repository records the result"*; `DESIGNED`
is *"the code or configuration is complete and on disk; nothing recorded has run it end to
end"*.

**2 · Amazon Bedrock is real in this repository and is not in the demo's request path.**
Titan embeddings and Claude inference were genuinely invoked, HTTP `200` with AWS request
ids committed (`evidence/aws/probe/bedrock-probe.json`). The four beats the deployed origin
answers are SQL against CockroachDB and nothing else. No model is called while a judge is
looking, and both halves of that sentence are true.

**3 · The second use case has no admission beat.** Use case one, the permit, refuses and then
admits — the four beats above. Use case two, the change request, has no fourth beat to give:
the deployment declares no merge route for a change request, and
`POST /v1/change-requests/{cr_id}/merge` measured `404` with the `404` body printing the whole
route table to prove the absence
([`docs/demo/research/r4-story.md`](../demo/research/r4-story.md) §1.2). The committed
transcript for that gate,
[`evidence/deploy/cr-gate-live.json`](../../evidence/deploy/cr-gate-live.json), carries verdict
`UNANSWERABLE` at `2026-08-16T04:41:54Z` for a neighbouring reason, and puts the distinction in
its own words: *"a route that has not been deployed is not a refusal that did not happen."*
Use case two is **told, not driven**. Open that file on the day you repeat this — it is the
measurement, and this paragraph is a snapshot of it.

A fourth limit is in the opener and is repeated because it is the easiest to forget: the
corpus is authored. The platform findings we measured against CockroachDB along the way are
catalogued separately; no story file is where a reader should first meet one.

<!-- word count: 1,383 — re-derive: python -c "print(len(open('docs/story/ORIGIN.md',encoding='utf-8').read().split()))" -->
<!-- layer-1 opener: 382 words (title to first '##') — re-derive: python -c "import re;t=open('docs/story/ORIGIN.md',encoding='utf-8').read();print(len(t.split('# ORIGIN')[1].split('\n',1)[1].split('\n## ')[0].split()))" -->
