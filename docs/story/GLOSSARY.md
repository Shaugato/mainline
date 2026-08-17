<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# GLOSSARY — one gloss per term, and where each term is defined for real

This corpus has a rule: **no term is used before it is defined.** This page is what makes
that rule enforceable across the story files, because it fixes *one* plain-language gloss per
term and every file uses that one. The gloss is the sentence a non-specialist can hold. It is
not the definition — the definition is in the file named beside it, and where the two differ
the file wins. The glosses below were fixed in
[`docs/submission/story-plan.md`](../submission/story-plan.md) §4 before any story file was
written, so that six files written at the same time could not drift apart on a word.

## The terms

| term | the gloss every story file uses | defined formally in |
|---|---|---|
| **clause** | one numbered rule inside a procedure — *"isolate at zero and verify"* | [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) — see the note below this table |
| **blame ancestry** | the chain of events that caused a rule to say what it says, held as database rows rather than as prose | `hackathon-research/research/05-architecture/commit-dag.md` §1 |
| **synchronic** | checking the world as it is right now | [`05-why-ancestry.md`](05-why-ancestry.md) |
| **diachronic** | checking what a decision depends on and what happened to it | [`05-why-ancestry.md`](05-why-ancestry.md) |
| **permit-to-work** | the form a supervisor signs before a crew opens a live machine | [`verticals/mainline/demo/USE-CASES.md`](../../verticals/mainline/demo/USE-CASES.md) |
| **obligation** | a debt the system raised against a decision — someone must answer it before the decision can complete | [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2 (§5.1 carries the row-level wording) |
| **disposition** | a named person's signed answer to one obligation | [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2 (§5.1) |
| **defeater** | one of the specific reasons the system will accept for setting an obligation aside — each is a question, not a checkbox | [`docs/demo/research/r4-story.md`](../demo/research/r4-story.md) §5 B6 |
| **projection** | a trigger copying a cross-row fact onto the row being written, derived from an authoritative table and never from whoever is writing | [`docs/submission/DEVPOST.md`](../submission/DEVPOST.md) *What it does*; normative at `TRAPPOINT-SPEC.md` §2.1 |
| **epoch** | a counter that increments whenever a new obligation appears, so a completed decision cannot have one attached afterwards | same; normative at `TRAPPOINT-SPEC.md` §2.2, rules `N-1` to `N-3` |
| **SQLSTATE** | the five-character code a database returns when it refuses — `23514` is a violated `CHECK` constraint, `P0001` is a trigger raising | PostgreSQL / CockroachDB standard; used at `TRAPPOINT-SPEC.md` §4 |
| **commit DAG** | a version history shaped like git's, where each version points at what it came from | `hackathon-research/research/05-architecture/commit-dag.md` §1–§3 |
| **MUS** | minimal unsatisfiable subset — the smallest set of reasons that explains a refusal | [`docs/demo/research/r4-story.md`](../demo/research/r4-story.md) §4.2; on screen at `verticals/mainline/demo/FIRST-RUN.md:86` |
| **canonicalisation** | turning a record into one exact byte string, so two runs on the same data hash identically | [`docs/adr/0041-checkpoint-wire-format.md`](../adr/0041-checkpoint-wire-format.md) |

**One citation above is inherited and imprecise, and is kept rather than quietly corrected.**
`spec/TRAPPOINT-SPEC.md` is the normative home of the kernel and it does not contain the word
*clause* — the specification is deliberately vertical-agnostic (§1.1, *out of scope*), and
clause rows are a MAINLINE thing. Where they are actually defined is
`verticals/mainline/db/migrations/0038_clause_blame_closure.sql` and the worked corpus in
`verticals/mainline/demo/USE-CASES.md`. The inherited pointer stays because five other files
were written against it and a silent change would split them; the correction is filed here
where a reader can see both.

## The verdict words

These are copied, never paraphrased, and never promoted. A row that loses its `DESIGNED` has
been upgraded, and that is the one edit this corpus forbids outright. The meanings are the
census's own, read from
[`evidence/tool-usage/crdb-features.json`](../../evidence/tool-usage/crdb-features.json)
(`verdict_meanings`):

| verdict | what it means, in the census's words |
|---|---|
| **`EXERCISED`** | *"it ran, and a committed artefact or a check in this repository records the result"* |
| **`DESIGNED`** | *"the code or configuration is complete and on disk; nothing recorded has run it end to end"* |
| **`NOT-AVAILABLE`** | *"checked on this platform and absent; no dependency was taken on it"* |

`DESIGNED` is not a soft `EXERCISED`. It is the word for *we built it and captured no run*,
and using it costs nothing next to being caught rounding it up. Two rows in that census carry
it today: CockroachDB Agent Skills and `CHANGEFEED`.

## Six more that appear in the story files

| term | the gloss | where it comes from |
|---|---|---|
| **gated subject** | the row the gate stands in front of — a permit or a change request — carrying an epoch and a projected counter, whose completing transition the database controls | `TRAPPOINT-SPEC.md` §5.1 |
| **PROJECT · PIN · REFUSE** | the three moves the refusal is made of: derive the fact, pin the completed decision to its epoch, refuse on a named constraint | `TRAPPOINT-SPEC.md` §2 |
| **admission** | the other half of a refusal — the same history going through once the debt has been signed for. A gate that only ever refuses is broken, not safe | `evidence/gate-refusal/` |
| **`PROVEN`** | the verdict a proof artefact carries when every beat it declared in advance came back as declared, with no failures. It is a statement about what that run measured and about nothing else | `evidence/deploy/live-gate-run.json` |
| **`STAGED`** | a field reproduced from the specification rather than produced by a database column. Where one is on screen, its label is on screen with it | `verticals/mainline/demo/FIRST-RUN.md:176-182` |
| **`SYNTHETIC — `** | the prefix carried by seed text. It is a column value, not a disclaimer added afterwards, and it is never cropped out to make a frame prettier | `verticals/mainline/demo/USE-CASES.md:29-32` |

## Two habits this vocabulary is meant to enforce

**A word with no file behind it does not go in.** Every row above names something a reader can
open. Where a gloss and its file disagree, the file is right and this page is a defect.

**The corpus is authored, and the vocabulary does not disguise it.** *Clause*, *incident*,
*site* and *operator* all name rows that were written for this project, not records of
anything that happened ([`docs/HONESTY.md`](../HONESTY.md)). The mechanism those rows move
through is real. The distinction is load-bearing and every story file states it on the same
screen it uses the corpus.

<!-- word count: 1,097 — re-derive: python -c "print(len(open('docs/story/GLOSSARY.md',encoding='utf-8').read().split()))" -->
<!-- layer-1 opener: 101 words (title to first '##') — re-derive: python -c "t=open('docs/story/GLOSSARY.md',encoding='utf-8').read();print(len(t.split('# GLOSSARY')[1].split('\n',1)[1].split('\n## ')[0].split()))" -->
