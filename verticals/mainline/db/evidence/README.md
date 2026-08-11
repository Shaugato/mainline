<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `db/evidence` — the ANN evidence database, and the exact size of its asterisk

**This directory is not in the apply path.** `discover()` globs
`verticals/mainline/db/migrations/*.sql`. Nothing here has a band number, nothing here appears in
`migrations.allocation.toml` or `migrations.lock.json`, and `trappoint migrate` never sees it.
`ann_evidence_schema.sql` is rendered by `scripts/aws/load_vectors.py` into a **separate
database**, `mainline_ann_evidence`, on the same cluster. It issues no statement against
`mainline_demo` and it cannot: the loader opens a different connection for it.

## Why a second database exists at all

`mainline_demo.mainline.clause_embedding` is the production sidecar and it is ready. It was
created empty by migration `0031`, it has the real `ce_ann` vector index, and before this fleet
ran on 2026-08-11 it held **0 rows**. The obstacle is not the sidecar. It is the sidecar's parent.

`evidence/aws/load/demo-row.json` carries `count_sequence` rather than a single before-and-after
pair, because the loader is re-runnable: on a first run the sequence is `[0, 1]`, and on a re-run
it is `[1, 0, 1]` — the middle number read *inside* the transaction, after the delete and before
the insert. Without that middle number an artefact cannot distinguish "the table still contains a
row" from "this run put one there", and only the second is the claim.

`mainline.clause_version` carries three triggers — `append_only`, `z_delta_witness_required`,
`clause_version_guard` — and `clause_embedding.fk_version` is a composite foreign key onto it.
To put a thousand corpus documents behind the real index in `mainline_demo`, you would first have
to put a thousand rows into `clause_version`, and every one of them would have to satisfy a
witness guard, a bloodline root, a canon digest and a control-delta lattice that exist precisely
so that rows which did not come out of the pipeline do not get in.

There are two honest responses to that and one dishonest one.

- **Dishonest:** disable the triggers, or synthesise witnesses until the guard passes, then
  report a corpus-scale ANN measurement on "the production table". The measurement would be real
  and the sentence describing it would be a lie by omission, because the thing that makes the
  production table the production table is the gate you took off.
- **Honest, and what this repository does:** measure the index where the index is identical and
  the parent is openly a stub, and separately put **exactly one row** through the production
  table under the full gate — a real Amazon Bedrock Titan vector for the one real
  `clause_version` that already exists, which the pipeline itself produced. Two claims, each
  the size of its evidence. `evidence/aws/load/demo-row.json` is the second one;
  `evidence/aws/load/cloud-load.json` is the first.
- **Also honest, and rejected on cost:** build the whole pipeline that legitimately produces a
  thousand `clause_version` rows. That is the product, not a demo, and it is not finished.
  Saying so is cheaper than pretending otherwise.

## What is identical, and how that is enforced rather than asserted

Lines 89–105 of `ann_evidence_schema.sql` are a **byte-identical copy** of lines 136–152 of
`verticals/mainline/db/migrations/0031_clause_embedding.sql` — the whole `CREATE TABLE
mainline.clause_embedding` statement, comments and column padding included.

That is checked, not claimed. The header of `ann_evidence_schema.sql` carries `@prov` ranges
which `scripts/aws/load_vectors.py` parses on every run. The ranges must be contiguous and cover
the file exactly; every `VERBATIM` range is compared line by line against its named source; a
single changed space fails the run and lands in `evidence/aws/load/schema-fidelity.json` as a
diff. The same artefact records the *server's* rendering — `SHOW CREATE TABLE` taken from
`mainline_demo` and from `mainline_ann_evidence` — because two files agreeing on disk is a
weaker fact than two clusters agreeing about what they built.

So the following are the same in both databases, and the artefact proves it each run:

| | |
|---|---|
| vector width | `VECTOR(1024)` — Titan v2's native output width |
| index | `VECTOR INDEX ce_ann (site_id, activity_root, embedding vector_cosine_ops)` |
| prefix columns | `site_id`, `activity_root`, in that order, both `NOT NULL` |
| distance operator | cosine (`vector_cosine_ops`) |
| primary key | `clause_embedding_pk (clause_uuid, commit_id)` |
| column families | `f_meta` and `f_vec`, the 4 KiB vector split off the metadata |
| CHECK constraints | `embed_model_stated`, `index_gen_stated` |
| the FK itself | `fk_version`, present and enforced |

## What the stub is, and exactly what it costs the claim

The stub is `mainline.clause_version` at lines 82–86: **two columns of the production table's
twenty-five, and none of its three triggers.**

```sql
CREATE TABLE mainline.clause_version (
  clause_uuid   UUID  NOT NULL,
  commit_id     BYTES NOT NULL,
  CONSTRAINT clause_version_stub_pk PRIMARY KEY (clause_uuid, commit_id)
);
```

It exists for one reason: `fk_version` names `(clause_uuid, commit_id)` and a foreign key needs
something unique to point at. In production those two columns are covered by
`UNIQUE INDEX cv_clause_commit_unique` on a table whose primary key is
`(clause_uuid, gen, commit_id)`. Here they *are* the primary key, because `gen` is one of the
twenty-three columns this table does not have.

**The cost, stated as plainly as it can be stated:**

1. **A row in `mainline_ann_evidence` proves nothing about admission.** The write gate is the
   thing that is missing. No result from this database may ever be quoted as evidence that a
   clause *could be created* in MAINLINE. That claim has exactly one piece of evidence in this
   repository — the single production row in `evidence/aws/load/demo-row.json` — and it is a
   claim about one row, not about a corpus.
2. **The prefix columns are client-supplied here, and in production they are supposed not to be.**
   Migration `0031`'s own header says `site_id` and `activity_root` are `PROJECTED` from
   `clause_version` / `clause` by a trigger in band 0130–0199, which must `RAISE P0001` when the
   parent version is absent. That band is not applied on the Cloud cluster: as measured on
   2026-08-11, `pg_trigger` returns **zero triggers on `clause_embedding` in `mainline_demo`**,
   so the production insert is *also* client-supplied today. The stub therefore costs nothing
   here that production is not already paying — but when the projection lands, this database will
   silently stop reflecting production on the one axis that decides reachability, and that is the
   first thing to re-check when band 0130–0199 applies.
3. **No generation semantics.** The production parent holds many generations of one clause and
   orders them; this one holds a pair of identifiers. Anything about supersession, `gen`
   monotonicity or bloodline is out of reach here by construction.
4. **No `mainline.clause`, `mainline.doc` or `mainline.commit_obj`.** The evidence rows have no
   document, no site record and no commit object behind them. `site_id` here is a UUIDv5 of a
   corpus operation name, not a foreign key to anything.
5. **No RLS, no grants, no `LOCALITY`, no `schema_locked` inheritance.** Whatever the cluster
   applies by default is what this database has; the artefact records the server's own
   `SHOW CREATE` for both databases so a reader can see any difference rather than trust this
   sentence.

## What the corpus is

**Synthetic.** Every document loaded here comes from `trappoint_recall.corpora.synthetic`, which
generates fatality reports, CSB reports, Australian regulator alerts and Part-50 lines from eight
hazard families. It is synthetic on purpose and the reason is the most creditable thing about the
corpus design: the real corpus is a register of people who died at work, and a repository is a
copy. Every artefact this loader writes carries `synthetic: true`. No number produced from this
database describes a real incident, and none of them may be presented as if it did.

## How much of the corpus is in here, and why it is not all of it

Every vector the `titan-embed` worker's manifest covers is loaded unconditionally, joined to the
corpus by the SHA-256 of the text each vector was made from — not by anybody's document-naming
convention, so the join cannot silently match nothing the day a convention changes.

What the loader embeds *itself*, for documents the manifest has not reached, is **capped**, and
the reason is a measurement rather than a preference. On 2026-08-11, `AWS/Bedrock` reported
**300 `Invocations` and roughly 3 800 `InvocationThrottles` per five-minute period** against
`amazon.titan-embed-text-v2:0` in `ap-southeast-2` while two workers of this fleet ran: the
account's on-demand ceiling is one call per second in total, and about nine of every ten requests
were refused. Embedding the whole corpus a second time here would have taken quota from the
worker whose job that is. The cap selects **width-first across `(site_id, activity_root)`** — one
document from every prefix pair before a second from any — so what it costs is corpus *depth* and
never a prefix tree, which is the only axis a prefix-constrained ANN measurement cannot lose.

`evidence/aws/load/cloud-load.json` carries the exact split: `documents_from_manifest`,
`documents_embedded_here`, `documents_dropped_by_cap`, and `documents_dropped_unembedded` — the
last being documents whose `InvokeModel` exhausted its throttle budget, listed by key rather than
rounded away.

## Reproducing it

```
.venv/Scripts/python.exe scripts/aws/load_vectors.py --fidelity-only     # no AWS, no cluster
.venv/Scripts/python.exe scripts/aws/load_vectors.py                     # the full load
```

The first form runs the provenance and byte-identity checks alone: no credentials, no network, no
database, **and it writes nothing**. It is the form a reviewer should run first, because it is the
one that decides whether anything else in this directory means what it says — and because a check
that overwrote the artefact it was checking would punish exactly the person who ran it.
