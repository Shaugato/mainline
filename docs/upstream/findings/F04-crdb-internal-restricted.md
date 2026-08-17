<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# F04 — the database will not describe itself, and the refusal does not say what to use instead

**Local arm: `REPRODUCED-TODAY` · Cloud arm: `ARCHIVED-EVIDENCE`, not re-run today.**
Both arms are labelled separately in §4 and neither is reported as the other.

---

## 1 · What happened

We asked the database a simple question about itself — *which of this table's indexes is the
special search index?* — and it refused to answer. The refusal told us how to switch the
restriction off but not what to use instead, and the afternoon we spent finding a way round it
turned up something we had not expected: on this version, no way of asking gives a clean answer.

---

## 2 · The words in that, in plain language

| Word | What it means here |
|---|---|
| **index** | A second copy of some of a table's data, arranged so a particular question can be answered without reading the whole table. |
| **vector index** | An index for "find me the rows most similar to this one" rather than "find me the row with this id". Ours is CockroachDB's C-SPANN. |
| **catalogue** | The database's own bookkeeping — its tables *about* itself. What tables exist, what indexes they carry, which machines are in the cluster, what background jobs are running. Every database has one; you read it with ordinary queries. |
| **`crdb_internal`** | CockroachDB's own catalogue, the detailed one. `system` is the even lower-level one underneath it. |
| **`information_schema`, `pg_catalog`** | The two catalogues CockroachDB provides for compatibility with the SQL standard and with PostgreSQL. Shallower than `crdb_internal`, and open. |
| **`SHOW` commands** | CockroachDB's own built-in questions — `SHOW INDEXES FROM t`, `SHOW CREATE TABLE t`. Not part of any catalogue; a separate surface again. |
| **SQLSTATE** | The five-character code returned with an error. `42501` means *insufficient privilege*. Same code, same meaning, every time, which is why we quote codes rather than error text. |
| **session variable** | A setting that lives on one open connection and disappears when it closes. Changes nothing for anybody else and nothing after you hang up. |
| **tier** | Which product you are running on. CockroachDB Cloud **Basic** is the free one — the one a hackathon entrant reaches for. A **local single-node** cluster is one copy of the database on one machine, where you are the administrator. **These are different exams.** |
| **scratch database** | A database created for one test run and dropped when it ends. Ours are named `upstream_f03_` followed by eight random characters. |

---

## 3 · Where we were wrong

**We filed this as a free-tier limitation. It is not one.**

`docs/diagnosis/divergence-05-schema-expectations.md:342` and this project's own summary of it
both frame the restriction as something CockroachDB Cloud Basic does. Measured today on a
**local single-node cluster**, connected as **`root`**, on a machine where we are the only
administrator and nothing had been configured, the refusal is **identical** — same SQLSTATE,
same message, same hint, on all six targets we asked for.

So the restriction is a **default of v26.2.5**, not a property of the free tier. Our original
sentence blamed the price of the product for a decision the version makes everywhere. That
correction makes the finding smaller and more useful at the same time: it is not "the cheap tier
hides things from you", it is "this is the default now, and the message you get does not finish
the sentence."

**One thing we still do not know, and will not guess at.** On the local node the escape hatch in
the message works. **We did not try it on Cloud Basic** and we are not going to — that would mean
issuing queries against a shared live cluster to test a setting we do not need. So this file says
nothing whatever about whether Basic lets you turn the restriction off. If you need that answer,
it is one `SET` away on your own cluster, and it is not in here because we did not measure it.

---

## 4 · The two exams

**These are two different exams and neither result is claimed for the other.**

### 4.1 · Local single-node — `REPRODUCED-TODAY`

`CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)`, connected
as `root` over `postgresql://root@localhost:26257`, run **2026-08-17** by
`scripts/upstream/repro_vector_and_catalogue.py` inside a scratch database it created and then
dropped. Transcript: `evidence/upstream/F04-crdb-internal-restricted.json`.

The scratch database gets a fresh random name on every run, so this document does not quote one.
The transcript records the exact name of the run that wrote it, under `exam.scratch_database`
and again under `teardown` (`created`, `dropped`, `confirmed_absent`), together with that run's
`started_at`.

Session left at its default (`allow_unsafe_internals` reads `off`):

| asked for | answer |
|---|---|
| `SELECT count(*) FROM crdb_internal.tables` | **refused, `42501`** |
| `SELECT count(*) FROM crdb_internal.table_indexes` | **refused, `42501`** |
| `SELECT count(*) FROM crdb_internal.jobs` | **refused, `42501`** |
| `SELECT count(*) FROM crdb_internal.gossip_nodes` | **refused, `42501`** |
| `SELECT crdb_internal.cluster_id()` | **refused, `42501`** |
| `SELECT count(*) FROM system.namespace` | **refused, `42501`** |
| `SELECT count(*) FROM information_schema.tables` | answered |
| `SELECT count(*) FROM pg_catalog.pg_class` | answered |

Six of six refused, and all six with the **same** message, verbatim:

```
Access to crdb_internal and system is restricted.
HINT: These interfaces are unsupported in production. To proceed, set the session variable
allow_unsafe_internals = true (not recommended), or contact Cockroach Labs for a supported
alternative.
```

Setting that variable on the connection made all six answer. It is session-scoped: the run set
it, re-read it as `on`, asked again, set it back to `false`, and closed the connection. Nothing
outside that connection changed.

### 4.2 · CockroachDB Cloud Basic — `ARCHIVED-EVIDENCE`, not re-run today

**Not re-run today, on purpose.** Re-running means issuing queries against a shared live cluster,
and nothing about this finding requires it. Cited by path and timestamp instead.

| artefact | captured | tier / role | asked for | answer |
|---|---|---|---|---|
| `evidence/deploy/judge-run.json`, probe `N02` | 2026-08-11T00:23:29Z | Cloud Basic `aws-ap-southeast-1`, role `mainline_judge`, direct SQL | a `crdb_internal` read | **`42501`**, message word-for-word the same as §4.1 |
| `evidence/deploy/judge-access.json`, `probe.negatives` | 2026-08-11T00:23:29Z | same | `SELECT count(*) FROM crdb_internal.jobs`, `… FROM crdb_internal.tables` | **`42501`**, same message (stored truncated at 200 characters; `judge-run.json` holds it whole) |
| `evidence/mcp/pack-run.json`, probe `N02` | 2026-08-16T07:33:46Z | Cloud Basic, through CockroachDB's **managed MCP server** at `https://cockroachlabs.cloud/mcp` | a `crdb_internal` read | refused with **different words**: `query references a restricted schema: access to "crdb_internal" is blocked for security reasons` |

That third row is a separate run five days later, and it is worth a second look. Asked through
CockroachDB's managed MCP server — the endpoint that lets an AI agent query the database — the
same restriction produces a *different* message, with no SQLSTATE, no hint, and no mention of the
session variable. An agent that had been taught to recover from the SQL-layer wording would not
recognise this one as the same wall.

---

## 5 · What is actually unavailable, and what merely needs a different question

**This is the part we got wrong the first time and the part worth reading.**

The honest complaint is *not* "we could not find out". We found out. The complaint is that the
surface a tutorial teaches is closed, and **the refusal does not name the surface that is open.**

Our real question was: *which indexes does this table have, and which of them is the vector one?*
That is two questions, and they do not have the same answer. All four routes below were asked of
the same table, in the same session, today:

| route | which indexes exist? | which one is a **vector** index? |
|---|---|---|
| `crdb_internal.table_indexes` | **refused `42501`** | **refused** — and see below for what it was hiding |
| `SHOW INDEXES FROM t` | **yes** — names `t_ann` | **no** |
| `pg_catalog` (`pg_class` joined to `pg_am`) | **yes** | **no** |
| `SHOW CREATE TABLE t` | **yes** | **yes** |

**`SHOW INDEXES` names the index but never says what kind it is.** On v26.2.5 it returns eleven
columns — `table_name`, `index_name`, `non_unique`, `seq_in_index`, `column_name`, `definition`,
`direction`, `storing`, `implicit`, `visible`, `visibility` — and not one of them is a type. The
vector index comes back looking like an ordinary one, its vector column listed with
`direction = 'ASC'` like any sortable column.

**The PostgreSQL-shaped route gives the same answer for two different things.** Joining
`pg_class` to `pg_am` — the standard way to ask an index what kind it is — reports the access
method as `prefix` for the vector index *and* `prefix` for the table's primary key. Two indexes
of genuinely different kinds, one answer. It cannot distinguish them either.

**`SHOW CREATE TABLE` answers it**, because it prints the definition as written:

```
CREATE TABLE public.t_clause_embedding (
    ...
    VECTOR INDEX t_ann (site_id, activity_root, embedding vector_cosine_ops)
) WITH (schema_locked = true);
```

### 5.1 · What was behind the wall, and why it matters that we looked

The first row of that table deserved more than a shrug, so with the escape hatch open on the same
connection we read every column of the table the refusal had been guarding. **We drafted this
finding believing the closed table would have given us a clean typed answer. It does not, and the
correction is the most useful thing in this file.**

`crdb_internal.table_indexes` has thirteen columns: `descriptor_id`, `descriptor_name`,
`index_id`, `index_name`, `index_type`, `is_unique`, `is_inverted`, `is_sharded`, `is_visible`,
`visibility`, `shard_bucket_count`, `created_at`, `create_statement`. For our two indexes:

| | `t_clause_embedding_pk` | `t_ann` (the vector index) |
|---|---|---|
| `index_type` | `primary` | **`secondary`** |
| `is_inverted` | `false` | **`false`** |
| `is_sharded` | `false` | `false` |
| `create_statement` | `CREATE UNIQUE INDEX …` | **`CREATE VECTOR INDEX t_ann ON …`** |

So the closed table *does* hold the answer — but only in the text of a printed `CREATE`
statement. Every one of its **typed** columns calls the vector index an ordinary secondary index.
There is no `is_vector`, and `index_type` does not have a value for it.

That is the real shape of this, and it is two things, only one of which is about the restriction:

1. **A closed surface with an unhelpful refusal** — `crdb_internal`, `42501`, a hint that names
   an escape hatch but not an alternative. This is the part that cost us the afternoon.
2. **A gap that has nothing to do with the restriction** — on v26.2.5, no catalogue anywhere
   offers a *typed, countable* column saying an index is a vector index. `index_type` says
   `secondary`, `is_inverted` says `false`, `pg_am` says `prefix`, `SHOW INDEXES` says nothing.
   The information exists in exactly one form, a `CREATE …` statement you have to pattern-match:
   openly through `SHOW CREATE TABLE`, and behind the wall through
   `crdb_internal.table_indexes.create_statement`. **Counting vector indexes on this version
   means matching a string.**

**A correction to our own tree, flagged not fixed.** `docs/demo/film/VO-CLOSE.md:1249` records
this refusal correctly and then advises publishing `SHOW INDEXES` as the one-command check for a
count of vector indexes. On v26.2.5 `SHOW INDEXES` cannot support that count — no column in it
distinguishes the kinds. `SHOW CREATE TABLE` can, by string match. That file belongs to another
owner in this wave, so this is a flag rather than an edit.

### 5.2 · The same gap, in a second place

There is a compact string that stands for the shape of a query plan — a *plan gist*. It is
exactly what an architecture document wants to quote so a later run can check itself against it.
Measured today, in one session, at the default setting:

```
EXPLAIN (GIST) SELECT 1
  -> AgICAgYC                                    answered

SELECT crdb_internal.decode_plan_gist('AgICAgYC')
  -> 42501 · Access to crdb_internal and system is restricted. HINT: …
```

You can produce the short form. You cannot read it back. The decoder lives in the closed part of
the catalogue and the refusal, again, does not name an open alternative. This is not a separate
finding — it is
the same one showing up somewhere it did real damage. Our finding **F03** was a claim about a
query plan, recorded on 2026-08-07 with no transcript. It was refuted by our own measurement on
2026-08-11 and was still standing in a public README on 2026-08-17. A plan identity that could
have been quoted into the document *and* read back later would have closed that in minutes.

---

## 6 · Why it cost us time

The restriction itself cost us minutes. What cost us the afternoon was the last clause of the
hint: *"or contact Cockroach Labs for a supported alternative."*

That sentence is the moment the trail goes cold. It confirms an alternative exists, declines to
name it, and points at a channel with a turnaround measured in days — during a build measured in
hours.

What we did next is recorded at `docs/demo/film/VO-CLOSE.md:1249`. Two routes were tried,
`crdb_internal.table_indexes` and the `pg_am` join, and neither produced a check worth handing to
a stranger. **The right call was made at that point and it is worth saying so:** rather than
publish a number it could not stand behind, that worker wrote *"this worker did not re-run it,
and says so rather than inheriting it silently."* The cost was not a wrong claim; the cost was a
claim that had to be left open, and an afternoon spent getting to that answer.

`SHOW CREATE TABLE` — the one open route that carries the answer at all — is not named by the
error, and is easy to pass over because it reads like a tool for a human at a terminal rather
than a way to ask the catalogue a question.

---

## 7 · Reproduce it

```
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe \
  scripts/upstream/repro_vector_and_catalogue.py
```

The script creates one scratch database, prints its name, does everything inside it, drops it in
a `finally:` block whether or not anything failed, and prints the name it dropped. It refuses to
run against anything that is not `localhost`. It touches nothing on CockroachDB Cloud, nothing
named `mainline_demo`, and no AWS service. The only setting it changes,
`allow_unsafe_internals`, lives on its own connection and dies with it.

---

## 8 · Provenance

| | |
|---|---|
| **Finding label** | **REPRODUCED-TODAY** (local arm) · **ARCHIVED-EVIDENCE** (Cloud arm) |
| **Version** | CockroachDB CCL v26.2.5 (built 2026/07/28 18:56:00) — on both arms |
| **Local exam** | local single-node CCL, user `root`, 2026-08-17 |
| **Cloud exam** | Cloud Basic, `aws-ap-southeast-1`, role `mainline_judge`, 2026-08-11 — **not re-run today** |
| **Not measured** | whether `allow_unsafe_internals` can be set on Cloud Basic. We did not try, and we do not guess. |
| **Reproduction** | `scripts/upstream/repro_vector_and_catalogue.py` |
| **Transcript** | `evidence/upstream/F04-crdb-internal-restricted.json` |
| **Archived artefacts** | `evidence/deploy/judge-run.json`, `evidence/deploy/judge-access.json`, `evidence/mcp/pack-run.json` |
| **Prior notes in this tree** | `docs/diagnosis/divergence-05-schema-expectations.md:342`, `docs/submission/census/crdb-four-tools.md:198`, `docs/demo/film/VO-CLOSE.md:1249` |
| **Nothing live was touched** | no CockroachDB Cloud query, no `mainline_demo`, no AWS call, no `GRANT`, `REVOKE`, `CONFIGURE ZONE` or cluster setting |

---

## 9 · What better would look like

**One concrete, implementable change: finish the sentence. Name the supported alternative in the
refusal itself.**

The hint already has the right shape and the right tone. It ends one clause too early:

> …or contact Cockroach Labs for a supported alternative.

If it ended instead with the surfaces that are open —

> …or use a supported alternative: the `SHOW` commands (`SHOW CREATE TABLE`, `SHOW INDEXES`),
> `information_schema`, or `pg_catalog`.

Those three are the surfaces this run measured open on the same connection, in the same session,
seconds after the refusal.

— then the afternoon does not happen. This is a one-line change to a static string. It needs no
new surface, no new privilege model, and no change to what is restricted or why. Every user who
hits `42501` on `crdb_internal` today is a user who now knows where to go next.

Two more, in the same spirit:

1. **Let one typed, countable column say that a vector index is a vector index.** Today none
   does: `crdb_internal.table_indexes.index_type` returns `secondary`, `is_inverted` returns
   `false`, `pg_am` returns `prefix` for it and for the primary key alike, and `SHOW INDEXES` has
   no type column at all. The fact exists only inside `CREATE …` statement text, so counting
   vector indexes means matching a string — which is exactly the kind of check that is wrong for
   six months before anybody notices. Either an `is_vector` boolean or a new `index_type` value
   would close it, on `SHOW INDEXES` (open by default, and its name already matches the question)
   and on `crdb_internal.table_indexes` alike. **This is the item here that has nothing to do
   with the restriction, and the one we would keep if we could only keep one.**
2. **Make the managed MCP server's refusal say the same thing the SQL layer says.** Right now the
   two channels reject the same query with different words, and only one of them mentions the
   session variable or carries a SQLSTATE. An agent that has learned to recover from one does not
   recognise the other.

Nothing here asks CockroachDB to unrestrict anything. Restricting `crdb_internal` by default is a
defensible call and we are not arguing with it. We are asking the refusal to be as helpful as the
rest of the product already is.
