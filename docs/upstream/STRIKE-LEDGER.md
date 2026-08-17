<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Strike ledger — what we thought we had found, and did not

This is the list of things we were going to tell CockroachDB and then did not, because when we
went back to check them they did not hold up.

**Findings struck: 1.** Of seven candidates, six are published in
[`COCKROACHDB-FIELD-NOTES.md`](COCKROACHDB-FIELD-NOTES.md) and one is here.

**Individual claims withdrawn from inside the six that survived: 6.** Those are listed in §3.
Several of them had already been published in our own README, which is the uncomfortable part
and the reason this page exists.

---

## 1 · Why a page like this exists at all

A list of complaints is easy to write and worth very little. What makes a complaint worth a
maintainer's time is that somebody tried to reproduce it *after* writing it down, on purpose,
hoping to fail.

So before publishing, one person who had written none of the findings re-ran every one of them
from a cold shell — a brand-new process with a clean environment, so that nothing left in memory
by an earlier run could make a later one look successful. That person's job was to strike things.
The program is [`scripts/upstream/verify_field_notes.py`](../../scripts/upstream/verify_field_notes.py)
and its output is [`evidence/upstream/verification.json`](../../evidence/upstream/verification.json).

**A wave that strikes nothing did not check.** If the number at the top of this page were zero,
the right conclusion would not be that we were right about everything; it would be that the
re-check was ceremonial. The number is 1, and the withdrawn-claims count is 6.

---

## 2 · The finding we struck

### F03 — "the vector index is not chosen by the planner at demo scale"

Three words used below, glossed once. An **index** is a second copy of some of a table's data,
arranged so one particular question can be answered without reading the whole table. A **vector
index** is one built for *"find me the rows most similar to this one"* rather than *"find me the
row with this id"*. A **query plan** — sometimes called an **optimizer plan** — is the database's
written-out decision about how it will answer a question, including which indexes it will read;
you ask for it by writing `EXPLAIN` in front of your query.

**What we expected to show.** That at roughly 5,200 rows, a similarity search that also filters on
two ordinary columns would *not* use the vector index — that the database would read the table and
filter afterwards — and that the index would only be used if we named it in the query with
`FROM table@index_name`.

**What we actually saw.** We tried twice. Both times the database used the index without being
asked. Re-run today on a local single-node cluster, at every table size we swept — 0, 200, 1,100
and 5,300 rows — the plan for the query that named *no* index contains a `vector search` step
reading the index. The plan with the hint and the plan without it are the same plan:

```
• vector search
    table: t_clause_embedding@t_ann
    target count: 10
    prefix spans: [/'5b144fe2…'/'/mill' - /'5b144fe2…'/'/mill']
```

**The refutation was already in our own tree before this wave started, and nobody had joined it
up.** A run on 2026-08-11 against CockroachDB Cloud recorded, in as many words,
`GT-06 reproduces: False` across the same sweep. The original note stayed in the README for ten
days after the evidence against it was written down.

**Why we struck it rather than softening it.** There is a version of this sentence that would have
survived — something about cost-based planners preferring a scan on a small table. We are not
writing that sentence, because we did not measure it. The claim we made was specific and testable,
we tested it, and it is false. Rewording a false specific claim into a true vague one is how a
document stops being checkable.

**What is genuinely left over**, and is not a complaint about the planner, is in §8 of the finding
file: `EXPLAIN` can produce a compact *plan gist* — a short string standing for a plan's shape —
but the function that turns a gist back into a readable plan lives in a schema that is closed by
default, which is [finding F04](findings/F04-crdb-internal-restricted.md). So the quotable form
exists and the way to read it back does not, for the same user in the same session. Had both
existed, this strike would have been a two-minute correction on 2026-08-11 instead of a
ten-day-old sentence in a public README.

Full account, including the plans in full and the sweep:
[`findings/F03-vector-index-not-chosen.md`](findings/F03-vector-index-not-chosen.md).
Transcript: [`evidence/upstream/F03-vector-index-not-chosen.json`](../../evidence/upstream/F03-vector-index-not-chosen.json).

---

## 3 · Claims withdrawn from inside findings that survived

These six findings are published, but each is **narrower than the sentence we started with**. In
every case the wider sentence is the one we had already written down somewhere, and the narrower
one is what we could actually demonstrate today.

| # | The claim we started with | What we can actually support | Where |
|---|---|---|---|
| 1 | `has_function_privilege()` is a stub that answers `true` for everybody and can never fail. | Only the form that names a role — `has_function_privilege('<role>', …)` — is blind. The form where a user asks about *itself* answers correctly. Calling the whole built-in a stub overstated it. | [F01](findings/F01-has-function-privilege.md) |
| 2 | `crdb_internal` and `system` are restricted **on the Basic tier**, so the free plan hides things from you. | The restriction is a **default of v26.2.5 everywhere**, including a local single-node cluster where you are the only administrator. We blamed the price of the product for a decision the version makes for everyone. | [F04](findings/F04-crdb-internal-restricted.md) |
| 3 | The 20,000-object ceiling "surfaces as unrelated failures, not as a clear quota error." | The error itself is **good** — it names the limit, the current count, and the setting to change. What cost us an hour is *where* it arrives and that nothing counts down towards it beforehand. | [F05](findings/F05-schema-object-cap.md) |
| 4 | `gc.ttlseconds` **defaults** to 4500 on CockroachDB Cloud Basic. | Withdrawn completely. 4500 was a value **we** set. The tool that recorded it kept the number and discarded the column saying who set it, so we read our own setting back as the platform's default. | [F06](findings/F06-gc-ttlseconds.md) |
| 5 | `convert_from()` returns an untyped `<string>` that `split_part` will not resolve without an explicit `::STRING`. | Withdrawn. Given a genuine bytes column, `convert_from` reports its return type as `text` and `split_part` takes it with no cast at all. We had read a fragment of an error message as a fact about a return type. | [F07](findings/F07-convert-from-untyped.md) |
| 6 | The same statement resolved on a local cluster while failing `42883` on Cloud. | Withdrawn. The thing that differed between our two runs was the **column type**, not the cluster. Our own comment four lines below the original note said so. | [F07](findings/F07-convert-from-untyped.md) |

Two of those — 1 and 4 — were the two the plan for this document set flagged in advance as the
most likely overclaims, and both turned out to be overclaims. One of them (4) is gone entirely;
the other (1) is now a smaller and more specific defect than the one we thought we had.

---

## 4 · Two judge-facing documents still carry a withdrawn claim

Flagged here, deliberately not fixed. Other people were rewriting those files in the same hour
this page was written, and editing underneath them would have collided.

| File | Line | What it still says | Status |
|---|---|---|---|
| [`README.md`](../../README.md) | 220 | *"At 5,200 rows, unless the index is named in the statement, the database scans and then filters"* | **struck** — see §2 |
| [`docs/submission/readme-parts/05-findings.md`](../submission/readme-parts/05-findings.md) | 27 | the same row, same citation | **struck** — see §2 |
| [`README.md`](../../README.md) | 217 | *"`has_function_privilege()` cannot answer `false` … for that login, for `root`, for `admin`, for `public`"* | **narrowed** — claim 1 in §3 |
| [`docs/adr/0002-g1-platform-ground-truth.md`](../adr/0002-g1-platform-ground-truth.md) | 20, 36 | GT-06, uncorrected | **struck** — see §2 |

**The first two are the ones that matter**, because both of them cite
[`evidence/aws/ann/explain-unhinted.txt`](../../evidence/aws/ann/explain-unhinted.txt) as their
proof, and a reader who opens that artefact finds the plan that refutes the sentence pointing at
it. A claim whose own cited evidence contradicts it is worse than no claim.

The paste-ready correction is in [`LINK-BLOCK.md`](LINK-BLOCK.md).

---

## 5 · What we did not strike, and why that is not a free pass

Six findings survived. That is not the same as six findings being important, and we would rather
say so here than have a reader discover it:

- **F02 and F05 are largely our own mistakes**, and both say so in their own opening. They are
  published because the platform half is real and small — two catalogue surfaces that spell one
  thing two ways, and a ceiling with no gauge — not because we think we were wronged.
- **F05's central refusal was not re-run today** and is labelled `ARCHIVED-EVIDENCE` for exactly
  that reason: re-triggering it means creating twenty thousand tables on purpose, and this is a
  finding *about* leaving twenty thousand tables lying around.
- **No finding here was measured on CockroachDB Cloud today.** The Cloud arms are all archived
  readings from earlier dates, labelled as such, because re-running them means driving statements
  at a shared live cluster.

---

## 6 · How to check this page

```
.venv/Scripts/python.exe scripts/upstream/verify_field_notes.py
```

It re-runs all four reproduction programs from a cold shell, checks each finding's page for
exactly one honesty label, a version and a hosting plan, re-derives the riskiest finding with its
own SQL rather than the original author's, and lists every database on the node before and after
so that a wave writing about orphaned databases cannot quietly leave more behind. It prints the
strike count as the last thing it does.

Read next: [`COCKROACHDB-FIELD-NOTES.md`](COCKROACHDB-FIELD-NOTES.md) for the six that survived,
and [`WHAT-WORKED.md`](WHAT-WORKED.md) for the three things that carried the product.
