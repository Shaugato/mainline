<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The MOC stream — declared scope, and the acts that carry a change request

## What this directory is for

`mainline.cr_clause` is the relation the change-request merge gate reads. Without it a change
register is a list of titles: `open_blocking` counts nothing, the MOC Ancestry Audit walks
nothing, and finding **S16** — *the repository is the protected branch and the permit is one of
its refs* — has no enforcement surface on the document side.

Stage 1 emitted the register (340 entries: sites, dates, intents, terminal states). Stage 1b
authored causality over clause revisions. Neither emitted scope. Before this stage, two anchored
spine revisions were the only place in the whole corpus where a clause change pointed at a change
record.

Regenerate with:

```
python -m mainline_corpus.moc_stream --out verticals/mainline/fixtures/corpus/moc-stream \
    --answer-key verticals/mainline/fixtures/corpus/answer-key
```

Two runs are byte-identical. The stage rebuilds stages 1 and 1b in memory rather than reading
them off disk; `--answer-key` is a **cross-check** — the rebuilt clause universe must agree with
the committed `clause.jsonl`, and a mismatch is a refusal naming the difference.

## The two things this stage refuses to do

**It does not mint commits.** Declared scope is pinned to a clause *version*, not to a clause:
`cr_clause`'s foreign key is onto `(clause_uuid, commit_id)`, so a re-authored clause cannot
silently carry an old declaration forward into text nobody read. `commit_id` is sha256 over a JCS
envelope and cannot be chosen. It is emitted `null` and registered in `pending.jsonl` — with
`commit_for_revision_key`, the natural key of the revision whose commit closes it, so the worker
that mints the DAG closes each row deterministically rather than by search.

**It does not mint the event chain.** `cr_event.chain_digest` is a `STORED` generated column the
*server* computes over CockroachDB's own JSONB rendering, and `mainline.fn_cr_event_chain`
(migration 0106) refuses any row whose `prev_digest` is not byte-equal to the stored
predecessor's. Reimplementing that normaliser in Python would stake the corpus's reproducibility
on our copy never diverging from the server's — and a digest the client can predict no longer
proves the server saw the payload it hashed. Migration 0118 step 3 shows the shipped answer:
`mainline.merge_change_request` *reads* the predecessor's `chain_digest`.

So this directory ships **`cr_transition_plan.jsonl`, not `cr_event.jsonl`**. It is an ordered
plan of acts, each naming the surface it must be performed through (`execute_via`), so the chain
is minted in the only place it can honestly be minted. Naming the file `cr_event.jsonl` would
have invited exactly the direct insert the chain exists to prevent.

## Files

| File | Table | What it is |
|---|---|---|
| `cr_clause.jsonl` | `mainline.cr_clause` | declared scope; `commit_id` null and registered pending |
| `cr_clause_registry.jsonl` | — | the basis of each declaration, the version it pins, the delta |
| `cr_transition_plan.jsonl` | — | the ordered acts the loader performs, in order, with actors |
| `moc_dossier.jsonl` | — | one row per change request: scope, plan shape, predicted precursors |
| `pending.jsonl` | — | every column left null, and who closes it |
| `pending_reasons.json` | — | the prose behind each `reason_code`, written once |
| `spine_change_request.json` | — | `MOC-2026-0413`: its one declared clause and the act its plan omits |
| `verify_report.json` | — | every check the database would eventually run, run here first |
| `index.json` | — | the manifest: digests, histograms, and this stage's own census |

## How a declaration comes to exist

Five bases. Four of them **read** a fact another generator already wrote down; only the fifth
draws, and it runs only where the other four are silent.

| Basis | Source |
|---|---|
| `skeleton:driving_change_ref` | stage 1 wrote the change record onto the document revision |
| `blame:proposed_revision` | the 2026 weakening already names `MOC-2026-0413` |
| `injector:weakening_chain` | each weakening step already names the MOC it hid behind |
| `injector:document_split` | each migrating clause already names its change record |
| `moc_stream:window` | authored here, from a reissue inside the change's window |

**The vehicle is not the cause.** A change request is the administrative vehicle through which an
edit reaches a controlled document; a blame edge is a claim about what *caused* the edit. They
are different relations with different evidential weight. So `moc_stream:window` binds only to
revisions whose driver is `routine_review`, `moc` or `regulator` — never `incident`. Binding an
MOC to an incident-driven revision would assert that a change record produced an edit the answer
key says an incident produced: a contradiction inside our own fixtures, and a false positive the
recall harness could never have detected.

A document's **first issue** is also excluded: that is the document coming into existence, not a
change to it, and nothing approved it through a register that had nothing yet to change.

One reissue may implement up to three approved changes, because that is what reissues do — a
controlled document is not reissued per change request, which is why change registers advance in
gaps while revision numbers advance by one. It is also the corpus's only natural source of two
subjects declaring the same clause, which is precisely the situation `open_conflicts` counts.

## What is claimed, and what is not

**Claimed.** The four read bases are facts other generators authored. Every row would satisfy
`cr_clause_relation_known`, `pk_cr_clause` and both foreign keys once `commit_id` is closed.
Every planned edge is checked against the seeded `change_request` edges parsed out of
`0017b_subject_transition_seed.sql` — the table is the authority, not our copy of it. Two runs
produce identical bytes.

**Not claimed.** `moc_stream:window` bindings are *authored*, not observed; they are labelled as
such on every row, and a recall experiment that treats them as ground truth for causation is
using them for something they do not support. `precursor_severity_max_from_answer_key` in the
dossier is a **prediction** written down so the projection can be checked against it — it is not
`sev_max`, it is loaded nowhere, and if it ever disagrees with what the triggers derive then the
corpus is wrong, which is exactly where that disagreement should surface.

`verify_report.json` reports `SKIP` as loudly as `FAIL`. A skipped check is a check that did not
run; it is never a check that passed.
