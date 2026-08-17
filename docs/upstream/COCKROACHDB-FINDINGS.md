<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Feedback for CockroachDB

*Our answer to the submission's optional requirement — "provide feedback on the CockroachDB AI
tools or features." Seven things surprised us while we built this product. Six of them we can
still demonstrate today. One of them turned out to be wrong, and it is in here too.*

---

## Sixty seconds, no jargon

We built a product whose entire claim is that **the database itself** refuses work that
contradicts a decision someone recorded earlier. Not a rule in our application that a second
application could walk past — a rule inside the table. CockroachDB can do that, which is why we
chose it.

Along the way we wrote down seven things about the platform that surprised us. Here is the one
that mattered most, with nothing in it you need to look up:

> We took away one test user's permission to run one small program stored inside the database.
> The database then refused to let that user run it — exactly as it should.
>
> But when we asked the database, in the same session and about that same user, *"is this user
> allowed to run it?"*, the database answered **yes**.
>
> We had a safety check in our own code that asked the database that question. It could never
> have caught anything. It had been green the whole time because it was incapable of being red.

That cost us an afternoon and, worse, a period of believing we were protected when we were not.
It is finding **F01** below.

**Before we go further: we started with seven and we are publishing six.** We re-ran every one of
them from scratch before writing this page, hoping to fail. One did not survive and has been
withdrawn; six individual sentences inside the survivors were withdrawn as well, several of which
we had already published in our own README. All of that is written down in
§[Reported, not reproduced on this machine](#reported-not-reproduced-on-this-machine) rather than
quietly deleted. **A list of complaints where nothing got struck is a list nobody checked.**

---

## What the platform got right, and we want to say it first

A critique with no praise is a grievance. Three things about CockroachDB carried this product, and
they are measured to the same standard as every complaint below — a program you can run, a
transcript you can open.

1. **The refusal belongs to the table, not to us.** CockroachDB carries named `CHECK` constraints
   *(a rule written into a table's own definition; the database refuses any row that breaks it,
   whoever is writing)* **and** triggers written in the database's own procedural language *(a
   small program the database runs itself when a row changes — no application calls it and none
   can decline it)*. Measured on a four-table toy written at by a plain database client with none
   of our code in the path: `23514` when the write is honest, `P0001` when the counter is forged
   to satisfy the rule. Drop either mechanism and the other still refuses.
2. **The strongest concurrency setting is what you get without asking.** `SERIALIZABLE` *(two
   transactions running at once are guaranteed to come out as if they had run one after the
   other)* is already in force on a brand-new connection, before anyone configures anything. We
   built no locking machinery, and our retry loop retries exactly one code, `40001`.
3. **The error codes are exact enough to put on screen as evidence.** A `23514` refusal carries
   the constraint's name in *its own field* rather than buried in English prose, so our code reads
   a field and never parses a message.

Full detail, with file and line for each: **[`WHAT-WORKED.md`](WHAT-WORKED.md)**.

**None of what follows is an excuse for anything we did not build.** These are rough edges on a
product that did the hard thing we needed.

---

## Where this page sits

This page is the **summary**, written so that one person can triage seven reports in one sitting.
Every finding here has a longer file behind it with the full transcript.

| If you want | Open |
|---|---|
| the seven, triaged, in one uniform shape | **this page** |
| the engineer's front door, with plain-language framing | [`COCKROACHDB-FIELD-NOTES.md`](COCKROACHDB-FIELD-NOTES.md) |
| one finding in full — every statement, every column | [`findings/F01`](findings/F01-has-function-privilege.md) … [`F07`](findings/F07-convert-from-untyped.md) |
| what we withdrew and what we saw instead | [`STRIKE-LEDGER.md`](STRIKE-LEDGER.md) |
| what worked | [`WHAT-WORKED.md`](WHAT-WORKED.md) |

**This page adds no claim that is not in those files, and where it and a finding file ever
disagree, the finding file is right.** It is a view over them, not a second source of truth.

---

## Words this page uses

Each is glossed here before it appears below.

| Word | What it means here |
|---|---|
| **SQLSTATE** | The five-character code a database attaches to an error, so a program can recognise a specific failure without reading English. `42501` means *"you do not have permission"*; `42883` means *"no function of that name takes those argument types"*. Codes are stable across versions, which is why we quote codes rather than message text. |
| **privilege** | Permission to do one specific thing to one specific object. **Granting** gives it; **revoking** takes it away. |
| **routine** (or **procedure**) | A chunk of SQL stored inside the database under a name. Applications run it by name instead of sending the SQL themselves. |
| **signature** | A routine's name plus the list of argument types it takes. Two routines may share a name with different arguments, so the signature is what identifies one. |
| **catalogue** | The tables a database keeps *about itself* — what exists, who owns it, who may use it. You read it with ordinary SQL. `crdb_internal` is CockroachDB's own detailed one; `information_schema` and `pg_catalog` are the standard-compatible, shallower ones. |
| **index** | A second copy of some of a table's data, arranged so one particular question can be answered without reading the whole table. A **vector index** is one built for *"find the rows most similar to this"* rather than *"find the row with this id"*. |
| **optimizer** / **query plan** | The database's written-out decision about *how* it will answer a question — which indexes it reads, in what order. You ask for it by writing `EXPLAIN` in front of a query. |
| **quota** | A ceiling on how many of something you may have. Here: schema objects. |
| **schema object** | A thing the database tracks in its own bookkeeping — a table, view, sequence, schema, database, or user-defined function. **Not a row.** A million rows in ten tables is ten-ish schema objects. |
| **zone configuration** | A small bundle of storage settings attached to a database, a table, or the whole cluster. An object with none of its own inherits from a cluster-wide fallback called `RANGE default`. |
| **GC TTL** (`gc.ttlseconds`) | When you update or delete a row, the old version is kept for a while before being garbage-collected. This is how many seconds "a while" is — and therefore how far into the past you can read. `4500` is 75 minutes. |
| **`AS OF SYSTEM TIME`** | The SQL that reads the database as it was at a past instant. It reaches back only as far as the GC TTL allows. |
| **scratch database** | A throwaway database created for one measurement and dropped straight after. Ours are named `upstream_f<NN>_<8 hex characters>`. |
| **tier** | Which hosting plan a measurement was taken on. CockroachDB Cloud **Basic** is the free plan — the one a hackathon entrant reaches for. A **local single-node** cluster is one copy of the database on one machine where you are the administrator. **These are two different exams, and a result on one is never claimed for the other.** |

---

## Version and machine — what every measurement below was taken against

**CockroachDB CCL v26.2.5** (`x86_64-pc-linux-gnu`, built 2026/07/28 18:56:00, go1.25.5),
**local single-node**, over `postgresql://root@localhost:26257/defaultdb`.

**We do not generalise beyond that version and that tier.** Where a Cloud Basic reading exists it
is an archived artefact from a stated earlier date, labelled, and never merged with a local one.

---

## The seven candidates, and what happened to each

| # | In one line | SQLSTATE | Verdict |
|---|---|---|---|
| **[F01](#f01--the-privilege-question-that-cannot-answer-no)** | Asked whether a *named* user may run a routine, the database answers `true` even after that user's permission was revoked and the engine itself refuses the call | engine refuses `42501`; **the question returns no error, just the wrong answer** | **published** |
| **[F02](#f02--one-routine-spelled-two-ways-and-no-key-to-join-them-on)** | Two catalogue surfaces spell one routine two different ways, and neither carries the other's spelling | none — a wrong answer, not an error | **published** *(mostly our bug)* |
| **[F03](#f03--the-vector-index-claim-struck)** | *"The vector index is not chosen by the optimizer at demo scale unless it is named"* | — | **STRUCK — refuted twice** |
| **[F04](#f04--the-database-will-not-describe-itself-and-the-refusal-does-not-say-what-to-use-instead)** | `crdb_internal` and `system` are closed by default; the refusal names an escape hatch it calls *not recommended* but never names the supported alternative | `42501` | **published** *(scope corrected)* |
| **[F05](#f05--a-ceiling-with-no-gauge)** | The ~20,000 schema-object ceiling is excellent when you hit it and invisible on the way up | `53400` | **published** *(mostly our mess)* |
| **[F06](#f06--a-setting-that-does-not-say-where-it-came-from)** | A zone-configuration readout returns the same number whether inherited or set by you; and the retention refusal never names the setting you must change | `XXUUU` | **published** *(original claim withdrawn entirely)* |
| **[F07](#f07--the-error-leads-with-the-name-of-the-call-that-worked)** | When one call is nested in another and the *inner* one fails, the message leads with the *outer* function's name | `42883` | **published** *(two claims withdrawn)* |

---

## The six findings

Each has the same five parts: **what we expected**, **what we measured**, **the command**, **what
it cost**, **what would have been better**.

---

### F01 · The privilege question that cannot answer "no"

**Full file:** [`findings/F01-has-function-privilege.md`](findings/F01-has-function-privilege.md) ·
**transcript:** [`evidence/upstream/F01-has-function-privilege.json`](../../evidence/upstream/F01-has-function-privilege.json)

**What we expected.** `has_function_privilege('<role>', '<routine>', 'EXECUTE')` exists so a
program can ask a permission question without trying the action and catching the failure. We
expected it to answer `false` after a `REVOKE` that the engine then enforces. That is the whole
purpose of the built-in — and `has_table_privilege`, the table-shaped equivalent, does exactly
that on the same build, in the same session.

**What we measured.** On a fresh scratch database we created a routine with the signature our
product ships, revoked `EXECUTE` from the test user **and** from `public` (the built-in
"everybody" role), and then asked both ways. The engine refused the call:

```
42501 user upstream_probe_<8 hex> does not have EXECUTE privilege on procedure merge_permit
```

The role-named form answered **`true` for every role we asked** — for the test user, for `root`,
for `admin`, for `public` — whether we named the routine by signature or by internal id. Eight
questions, eight `true`s.

| how you call it | what it means | what it answered |
|---|---|---|
| `has_function_privilege('<role>', '<routine>', 'EXECUTE')` | *may **that** role run it?* | **`true`** — wrong |
| `has_function_privilege('<routine>', 'EXECUTE')` | *may **I** run it?* | `false` for the refused user — right |

**Only the role-named form is blind — and that is the form a checking program has to use**, because
a checking program asks about somebody other than itself.

*It is not failing to resolve its arguments.* Two controls rule out the dull explanation — a
nonexistent routine returns `42883`, a nonexistent role returns `42704`. The `true` is a decision
reached *after* both arguments resolved.

*The negative control, same database, same session:* `has_table_privilege` answered `true` for a
`SELECT` that succeeded and **`false`** for an `INSERT` that was refused `42501`. Same shape of
question, one function tracks the engine and the other does not.

*(The 8-hex suffix is random per run — your copy will show different characters.)*

**Reproduce it.**

```
.venv/Scripts/python.exe scripts/upstream/repro_privileges.py
```

**What it cost.** An afternoon — and before that, a stretch of believing a guard was protecting us
when it was structurally incapable of failing. We found it only because we planted a deliberate
violation and the guard stayed green. The replacement reads `SHOW GRANTS` and expands role
membership by hand, which costs us the two things the built-in would have done for free.
**A check nobody has ever seen fail is not evidence of health.**

**What would have been better.** Make the role-named form resolve `EXECUTE` through the same path
the executor uses — the path `has_table_privilege` already uses successfully on this build — so
that it is *able* to return `false`. A permission-inspection built-in that cannot return `false`
is worse than one that does not exist, because programs get written against it.

If that is not near-term work, we would happily have taken the documentation fix instead: **one
line on the `has_function_privilege` page saying the role-named form does not currently reflect
routine `EXECUTE` grants.** That line would have saved the afternoon, and it is a pull request
rather than a project.

---

### F02 · One routine spelled two ways, and no key to join them on

**Full file:** [`findings/F02-show-grants-signature.md`](findings/F02-show-grants-signature.md) ·
**transcript:** [`evidence/upstream/F02-show-grants-signature.json`](../../evidence/upstream/F02-show-grants-signature.json)

**This one is our bug**, and it is here because admitting it is what makes F01 worth reading.

**What we expected.** That two catalogue surfaces describing the same routine in the same database
would agree on its name closely enough to compare, or would ship an identifier to join them on.

**What we measured.** They spell it differently, and neither carries the other's spelling:

```
SHOW GRANTS
    object_name  -> merge_permit(uuid, bytea, text, text, jsonb, bytea, int2, bytea)

SELECT routine_name FROM information_schema.routines
    routine_name -> merge_permit
```

We listed all 82 columns `information_schema.routines` offers; **none holds the argument list.**
In the same run, after granting the permission and *watching the user actually run the routine*,
our original comparison said:

```
looked for : 'merge_permit'                                                      (information_schema)
looked in  : ['merge_permit(uuid, bytea, text, text, jsonb, bytea, int2, bytea)'] (SHOW GRANTS)
matched    : False        <- WRONG. The user had just successfully run it.
```

There is a trap inside the trap: **the types are renamed on the way through.** We declared the
routine with CockroachDB's own type names and the catalogue echoed back the PostgreSQL ones —
`STRING` → `text`, `BYTES` → `bytea` — so building the expected string from your own
`CREATE PROCEDURE` does not match either. A working bridge exists,
`pg_get_function_identity_arguments()`, but nothing in either surface points at it and you only
go looking once you already know you have the bug.

**Reproduce it.**

```
.venv/Scripts/python.exe scripts/upstream/repro_privileges.py
```

**What it cost.** A wrong conclusion in a single afternoon — a false alarm on every routine, every
run. **The mirror image is worse and is why we treat it as more than a typo:** the same mismatch,
phrased as *"did everything match?"*, passes silently forever, because nothing ever matches and
nothing ever objects.

**What would have been better.** **Add the object's internal id as an eighth column on `SHOW
GRANTS`.** It already returns seven; a stable identifier would let anyone join grant output to
`pg_proc` on a key instead of by string surgery, making this whole class of mismatch impossible
rather than merely avoidable. Cheaper and still worth having: a sentence on the `SHOW GRANTS`
documentation page noting that routines appear with their full signature while
`information_schema.routines` does not, naming `pg_get_function_identity_arguments()` as the
bridge.

---

### F04 · The database will not describe itself, and the refusal does not say what to use instead

**Full file:** [`findings/F04-crdb-internal-restricted.md`](findings/F04-crdb-internal-restricted.md) ·
**transcript:** [`evidence/upstream/F04-crdb-internal-restricted.json`](../../evidence/upstream/F04-crdb-internal-restricted.json)

**We corrected our own scope on this one.** We had filed it as a free-tier limitation. It is not
one — measured on a local single-node cluster as `root`, where we are the only administrator, the
refusal is **identical**. It is a **default of v26.2.5**, not a property of the cheap tier. Our
original sentence blamed the price of the product for a decision the version makes for everyone.

**What we expected.** To be able to ask the database a simple question about itself — *which of
this table's indexes is the vector one?* — through the catalogue a tutorial teaches.

**What we measured.** Six of six `crdb_internal` and `system` reads refused, all with the same
message, while `information_schema` and `pg_catalog` answered on the same connection:

```
Access to crdb_internal and system is restricted.
HINT: These interfaces are unsupported in production. To proceed, set the session variable
allow_unsafe_internals = true (not recommended), or contact Cockroach Labs for a supported
alternative.
```

**The honest complaint is not "we could not find out". We found out.** It is that the surface a
tutorial teaches is closed and **the refusal does not name the surface that is open.** Four routes,
same table, same session:

| route | which indexes exist? | which one is a **vector** index? |
|---|---|---|
| `crdb_internal.table_indexes` | **refused `42501`** | **refused** |
| `SHOW INDEXES FROM t` | yes | **no** |
| `pg_catalog` (`pg_class` ⋈ `pg_am`) | yes | **no** — reports `prefix` for the vector index *and* for the primary key |
| `SHOW CREATE TABLE t` | yes | **yes** |

**And the correction that is the most useful thing in the file:** we opened the closed table with
the escape hatch to see what we had been missing, expecting a clean typed answer. There is none.
`index_type` reads `secondary` for the vector index, `is_inverted` reads `false`, and there is no
`is_vector`. The fact exists on this version in exactly one form — the text of a `CREATE …`
statement. **Counting vector indexes on v26.2.5 means matching a string.**

The same gap bites twice: `EXPLAIN (GIST)` produces a compact plan identity, but
`crdb_internal.decode_plan_gist()` — the function that reads it back — is behind the same wall.
You can produce the short form and cannot read it back.

**Reproduce it.**

```
.venv/Scripts/python.exe scripts/upstream/repro_vector_and_catalogue.py
```

**What it cost.** The restriction cost minutes. The last clause of the hint cost the afternoon:
*"or contact Cockroach Labs for a supported alternative"* confirms an alternative exists, declines
to name it, and points at a channel with a turnaround measured in days — during a build measured
in hours. And it cost us F03: a plan identity we could have quoted into a document *and* read back
later would have caught that false claim in minutes instead of leaving it in a public README for
ten days.

**What would have been better.** **Finish the sentence — name the supported alternative in the
refusal itself.** The hint has the right shape and ends one clause early. If it ended instead with
*"…or use a supported alternative: the `SHOW` commands (`SHOW CREATE TABLE`, `SHOW INDEXES`),
`information_schema`, or `pg_catalog`"* — the three surfaces this run measured **open on the same
connection, seconds after the refusal** — the afternoon does not happen. It is a one-line change to
a static string; it needs no new surface, no new privilege model, and no change to what is
restricted or why.

Two more in the same spirit: **let one typed, countable column say that a vector index is a vector
index** (this is the item we would keep if we could only keep one, and it has nothing to do with
the restriction); and **make the managed MCP server's refusal say what the SQL layer says** — asked
through it, the same restriction produces different words, no SQLSTATE, and no mention of the
session variable, so an agent taught to recover from one wording does not recognise the other.

**We are not asking CockroachDB to unrestrict anything.** Restricting `crdb_internal` by default
is a defensible call. We are asking the refusal to be as helpful as the rest of the product is.

---

### F05 · A ceiling with no gauge

**Full file:** [`findings/F05-schema-object-cap.md`](findings/F05-schema-object-cap.md) ·
**transcript:** [`evidence/upstream/F05-schema-object-cap.json`](../../evidence/upstream/F05-schema-object-cap.json)

**The mess was ours.** Our test suite went from all-green to thirteen broken tests overnight, and
for most of an hour it looked as though a code change had broken it. Nothing had — we had spent
weeks making throwaway copies of our database for tests and never deleting them. What we are
sending upstream is the shape of how we found out.

**What we expected.** That a resource we were consuming steadily would be visible before it ran
out — a gauge, a warning, or at minimum a supported way to ask *"how close am I?"*

**What we measured.** The ceiling is a cluster setting reading `20000`. A test database holding a
full copy of our schema costs about **146** objects, so roughly 137 copies fill the cluster. When
we hit it there were **242** databases holding **20,270** objects between them.

**We are correcting our own brief here.** It was handed to us worded *"the cap surfaces as
unrelated failures rather than as a quota error a reader can act on."* **The second half is wrong
and is not published.** The message is excellent — it states the maximum, the current count, and
the exact setting to change:

```
psycopg.errors.ConfigurationLimitExceeded: error executing StatementPhase stage 1 of 1 with
17 MutationType ops: cannot create new schema object(s): would exceed approximate maximum
(20000); current count: 20270
HINT:  You can increase the limit by adjusting the cluster setting sql.schema.approx_max_object_count
```

**What actually cost the time is *where* it arrives.** Every failure happened in fixture setup —
the preparation step before a test's own code — so the framework attributed each to the test whose
setup it was. A reader sees thirteen named tests in files nobody had touched, with the quota
message inside each traceback rather than in the summary:

| run | collected | passed | failed | errors |
|---|---|---|---|---|
| baseline | 1070 | 1069 | 0 | 0 |
| the saturated node | 1070 | **1056** | **1** | **12** |

**And nothing counts down.** Reproduced today, read-only: creating a database on a node at 19.4 %
of the ceiling emitted **0** notices. There is no threshold at which anything says *"you are
getting close"*, and the internal view that knows the count is the one F04 closes. So we counted
by hand out of the catalogue — an approximation, and labelled as one, because the server counts
descriptors and we counted catalogue rows. **A team cannot manage a budget it can only estimate.**

**Reproduce what can be reproduced.**

```
.venv/Scripts/python.exe scripts/upstream/repro_limits.py
```

*The refusal itself is not re-triggered — see
[Reported, not reproduced](#reported-not-reproduced-on-this-machine).*

**What it cost.** Most of an hour on the wrong hypothesis, spent proving a code change innocent:
checking the collected count had not moved, that every changed file was Markdown, that both suite
paths were byte-identical to the last commit. All real work, none of it the answer.

**What would have been better.** **Emit a `NOTICE` on schema-creating statements once the object
count crosses a fraction of the ceiling** — say 80 %, with the fraction itself a cluster setting so
a team can turn it off. The counting machinery already exists: the `CREATE` path computes the
current count *in order to refuse*, so the same number is available on the statements that succeed.
A team that saw `16,412 of 20,000 schema objects used` once a week would have dropped its leftovers
in minutes instead of meeting the ceiling in a red test report.

The cheaper half, if the notice is unwelcome: **make the count readable without `crdb_internal`** —
a single supported row, or a column beside the cluster setting. Today the only honest answer to
*"how close am I?"* is a hand-rolled sum the server itself would not agree with.

---

### F06 · A setting that does not say where it came from

**Full file:** [`findings/F06-gc-ttlseconds.md`](findings/F06-gc-ttlseconds.md) ·
**transcript:** [`evidence/upstream/F06-gc-ttlseconds.json`](../../evidence/upstream/F06-gc-ttlseconds.json)

**The claim we started with is struck before anything else.** We had written — in several of our
own documents — that `gc.ttlseconds` **defaults** to 4500 on CockroachDB Cloud Basic. **We cannot
support it and it is not claimed here.** The tool that read the number had just set that same
number itself, and it discarded the part of the answer that says where a value came from.

**What we expected.** That a settings readout would carry its own provenance in the part you would
naturally capture — that *"the platform handed me this"* and *"we set this"* would not look
identical.

**What we measured.** Three statements on a database created seconds earlier and configured by
nobody:

```
$ SHOW ZONE CONFIGURATION FOR RANGE default
target: RANGE default
        ALTER RANGE default CONFIGURE ZONE USING gc.ttlseconds = 4500, ...

$ SHOW ZONE CONFIGURATION FOR DATABASE upstream_f05_<8 hex>
target: RANGE default              <-- inherited; this database has none of its own
        ALTER RANGE default CONFIGURE ZONE USING gc.ttlseconds = 4500,

$ ALTER DATABASE upstream_f05_<8 hex> CONFIGURE ZONE USING gc.ttlseconds = 4500
$ SHOW ZONE CONFIGURATION FOR DATABASE upstream_f05_<8 hex>
target: DATABASE upstream_f05_<8 hex>   <-- now it has one of its own
        ALTER DATABASE upstream_f05_<8 hex> CONFIGURE ZONE USING gc.ttlseconds = 4500,
```

**The number is 4500 in both states.** Only the *target* column separates them. Our deployment tool
lifted the value out with a regular expression and never read `row[0]`.
**CockroachDB disclosed the provenance twice — in the target column and in the first line of the
rendered statement — and we stored neither.** That is the honest summary, and it is why the ask
below is a small one.

**The second half, reproduced today: neither failure names the setting.** A read past the retention
window is refused:

```
ERROR (XXUUU): batch timestamp 1786978495.862868698,0 must be after replica
               GC threshold 1786981181.723324325,0 (r9533: /{Table/1248-Max})
```

Four things about that message: it **never says `gc.ttlseconds`**, the one thing you must change;
it **never names the table or database**, only a range id and a key span; its SQLSTATE is `XXUUU`,
the code used when no more specific one applies — so a caller wanting to catch *"too far back,
retry closer to now"* has nothing stable to catch; and the window **is** recoverable from the
message, but only by arithmetic on the two timestamps, which yields 4514.1 s at -2h, -5h and -24h
alike. A satisfying consistency check, and a strange way to have to learn your own setting.

**Reproduce it.**

```
.venv/Scripts/python.exe scripts/upstream/repro_limits.py
```

**What it cost.** A published claim we could not support, which spread through our own documents —
one of them saying 4500 is *"the value Cloud Basic enforces"*, which is stronger again than
"defaults to", and which our own artefact contradicts by showing a `CONFIGURE ZONE` being
*accepted* on that cluster. What was **real** and is not withdrawn: the window in force on our
Cloud Basic database was 4500 s where our architecture had assumed 14400, and every design of ours
reaching into the past was re-scoped around roughly one hour as a result.

**What would have been better.** **One comment line at the head of an inherited rendering.** Today
`SHOW ZONE CONFIGURATION FOR DATABASE x`, answered by inheritance, renders
`ALTER RANGE default CONFIGURE ZONE USING …` — a statement which, copied out and run, changes a
**cluster-wide** default rather than that database. This would remove the hazard and carry the
provenance into every screenshot, paste and regular expression that follows:

```
-- DATABASE x has no zone configuration of its own; these settings apply via RANGE default
ALTER RANGE default CONFIGURE ZONE USING
        gc.ttlseconds = 4500,
```

**We would not have written the struck sentence had that line been in front of us.**

And: **give the retention refusal a stable, specific SQLSTATE outside the catch-all class, and name
the setting in the text** — *"… exceeds the 4500 s retention window (`gc.ttlseconds`) for
`db.schema.table`"*. Both numbers are already in the message; the sentence just does not spend them
on the reader. Running past your history window is an ordinary, expected, configured outcome, and
it is the one error in this whole build we could not catch by its code.

---

### F07 · The error leads with the name of the call that worked

**Full file:** [`findings/F07-convert-from-untyped.md`](findings/F07-convert-from-untyped.md) ·
**transcript:** [`evidence/upstream/F07-convert-from-untyped.json`](../../evidence/upstream/F07-convert-from-untyped.json)

**Most of this one is ours, and it is worth saying twice.** We passed a text column to a function
that takes bytes. The database refused it, returned the right SQLSTATE, and printed a hint telling
us to add a cast. **The finding is not that it was refused. The finding is which name the refusal
leads with.**

**What we expected.** That an error about an unresolvable call would lead with the name of the call
that failed — the first token being the thing you go and look at.

**What we measured.** Called on its own, the message is exactly right:

```
SELECT convert_from(checkpoint.body, 'utf8') FROM checkpoint;
ERROR  42883  unknown signature: convert_from(string, string)
HINT:  No function matches the given name and argument types. You might need to add explicit type casts.
```

Wrap the identical mistake in another call, and the name that leads changes to the call that was
fine:

```
SELECT split_part(convert_from(checkpoint.body, 'utf8'), chr(10), 3) FROM checkpoint;
ERROR  42883  split_part(): unknown signature: convert_from(string, string) (returning <string>)
```

Nest further and the names accumulate, innermost last —
`upper(): split_part(): unknown signature: convert_from(string, string) …`. Swap either function
and the shape holds, so it is not about these two in particular.

**Reproduce it.**

```
.venv/Scripts/python.exe scripts/upstream/repro_semantics_and_praise.py
```

**What it cost.** Two attempts spent fixing the wrong function. The three facts a reader needs are
all in that one line and they are in the wrong order of prominence: the name that **leads** is the
call that resolved; the name in the **middle** is the call that did not; and the fragment at the
**end**, `(returning <string>)`, looks like a claim about the inner call's return type while being
attached to the outer one. We read it as *"convert_from handed back something untyped"* and started
casting the result. The actual fix was to stop passing text to a function that takes bytes.

**What would have been better.** **Lead with the call that failed and name the callers after it.**
Same line count, same content, different order:

```
ERROR  42883  unknown signature: convert_from(string, string)
              in argument 1 of split_part()
HINT:  No function matches the given name and argument types. You might need to add explicit type casts.
```

If the current order must stay for compatibility, **the argument position alone would do most of
the work**: `split_part(): argument 1: unknown signature: convert_from(string, string)` puts a
pointer in front of the reader that the current message leaves them to infer.

---

## Reported, not reproduced on this machine

**This section is the point of the page.** Everything below was written down during the build and
is *not* published above, because we could not stand behind it today. Each says why.

### F03 · The vector-index claim, struck

**We do not report this as unreproduced. We report it as refuted**, which is stronger and worse for
us.

**What we had written.** That at roughly 5,200 rows, a similarity search filtering on two ordinary
columns would *not* use the vector index — the database would scan the table and filter afterwards
— and the index would be traversed only if named explicitly with `FROM table@index_name`.

**What we saw when we checked.** We tried twice. **Both times the database used the index without
being asked.** Re-run on a local single-node cluster at every table size we swept — 0, 200, 1,100
and 5,300 rows — the plan for the query naming *no* index contains a vector-search step reading the
index. The hinted plan and the unhinted plan are the same plan:

```
• vector search
    table: t_clause_embedding@t_ann
    target count: 10
```

**The refutation was already in our own tree and nobody had joined it up.** A run on 2026-08-11
recorded `GT-06 reproduces: False` across the same sweep. The claim stayed in a public README for
ten days after the evidence against it was written down, **citing as its proof an artefact that
contains the plan refuting it.** A claim whose own cited evidence contradicts it is worse than no
claim.

**Why struck rather than softened.** There is a version of this sentence that would have survived —
something vague about cost-based planners preferring a scan on a small table. We are not writing
it, because we did not measure it. **Rewording a false specific claim into a true vague one is how
a document stops being checkable.**

Full account and the plans in full: [`STRIKE-LEDGER.md`](STRIKE-LEDGER.md) §2 and
[`findings/F03-vector-index-not-chosen.md`](findings/F03-vector-index-not-chosen.md).

### F05's central refusal · archived, and deliberately not re-triggered

The 20,000-object refusal itself was recorded on **2026-08-16** and again on **2026-08-17**, and is
cited above from the run that produced it. **It was not re-triggered for this page and could not
honestly be: re-triggering means creating twenty thousand schema objects on purpose, and this is a
finding *about* leaving twenty thousand schema objects lying around.** Everything measurable
without doing that — the ceiling setting, the object census, the absence of any notice, the closed
counting view — **was** re-measured today, read-only, and is marked as such in place.

### Every CockroachDB Cloud Basic reading · archived, not re-run

**No finding on this page was measured on CockroachDB Cloud today, and this wave issued no
statement against any Cloud cluster.** The reason is a rule we are working under and it is a good
one: re-running these means driving statements at a **shared live cluster** that is currently
frozen for judging. A finding is not worth breaking a freeze for.

| Finding | The Cloud reading | Captured | Why not re-run |
|---|---|---|---|
| **F04** | the same `42501` restriction, message word-for-word, on Basic `aws-ap-southeast-1`; and a *differently worded* refusal through the managed MCP server | 2026-08-11, 2026-08-16 | shared live cluster |
| **F06** | `gc.ttlseconds` read as `4500`, and a `CONFIGURE ZONE` accepted | 2026-08-07, 2026-08-10 | shared live cluster; **and the reading is why the claim was withdrawn** — no artefact recorded the target |
| **F07** | the original observation that the statement behaved differently on Cloud | 2026-08-07 | needs tables and rows created on a cluster others are using — **and the claim was withdrawn anyway**, see below |

**One thing we specifically did not measure and will not guess at:** whether
`allow_unsafe_internals` can be set on CockroachDB Cloud Basic. On the local node the escape hatch
works. We did not try it on Basic, so this page says nothing about it.

### Sentences from our own earlier notes that did not survive re-measurement

Six claims were withdrawn from inside the six findings that survived. **In every case the wider
sentence is one we had already written down somewhere, and the narrower one is what we could
actually demonstrate.**

| The claim we started with | What we can actually support |
|---|---|
| `has_function_privilege()` is a stub answering `true` for everybody and can never fail. | Only the **role-named** form is blind. The form where a user asks about *itself* answers correctly. Calling the whole built-in a stub overstated it. |
| `crdb_internal` and `system` are restricted **on the Basic tier**, so the free plan hides things from you. | The restriction is a **default of v26.2.5 everywhere**, including a local cluster where you are the only administrator. We blamed the price for a decision the version makes for everyone. |
| The 20,000-object ceiling "surfaces as unrelated failures, not as a clear quota error." | **The error itself is good** — it names the limit, the count, and the setting. What cost an hour is *where* it arrives and that nothing counts down. |
| `gc.ttlseconds` **defaults** to 4500 on Cloud Basic. | **Withdrawn completely.** 4500 was a value *we* set; our tool kept the number and discarded the column saying who set it. |
| `convert_from()` returns an untyped `<string>` that `split_part` will not resolve without an explicit `::STRING`. | **Withdrawn.** Given a genuine bytes column, `convert_from` reports its return type as `text` and `split_part` takes it with no cast at all. We had read a fragment of an error message as a fact about a return type. |
| The same statement resolved locally while failing `42883` on Cloud. | **Withdrawn.** What differed between the two runs was the **column type**, not the cluster — and our own comment four lines below the original note said so. |

**Two of these — the first and the fourth — were flagged in advance as the most likely overclaims,
and both turned out to be overclaims.** That is the process working, and it is the reason we would
rather publish six things you can check than seven with one we cannot.

---

## What we are not claiming

- **Nothing here was measured on CockroachDB Cloud today.** Cloud readings are archived artefacts
  from stated earlier dates and are not presented as fresh measurements.
- **A result on one tier is not claimed for another**, and a result on one version is not claimed
  for another. Everything above is v26.2.5.
- **We did not read CockroachDB's source.** These are behaviours with programs attached, not
  diagnoses. Where we cannot explain a cause, we say we cannot.
- **These are not severity ratings and this is not a security report.**
- **None of this has been sent to Cockroach Labs yet.** This document set is the thing we would
  send.
- **Nothing here excuses anything we did not build.** Our own gaps are listed in
  [`docs/HONESTY.md`](../HONESTY.md), not here.

---

## How to check this page, including us

Every finding names the program that produces it:

```
.venv/Scripts/python.exe scripts/upstream/repro_privileges.py             # F01, F02
.venv/Scripts/python.exe scripts/upstream/repro_vector_and_catalogue.py   # F04 (and struck F03)
.venv/Scripts/python.exe scripts/upstream/repro_limits.py                 # F05, F06
.venv/Scripts/python.exe scripts/upstream/repro_semantics_and_praise.py   # F07, and what worked
```

Each creates one scratch database, prints the name it created and the name it dropped, drops it in
a `finally` block so it goes even on the error path, and reports how many databases it left behind
— a number that must be zero. **None touches a CockroachDB Cloud cluster, makes an AWS call, or
prints a credential.**

And to check all of them at once, including us:

```
.venv/Scripts/python.exe scripts/upstream/verify_field_notes.py
```

That program was written by someone who wrote none of the findings, and **its purpose is to strike
them.** It re-runs all four programs from a cold shell — a fresh process with a clean environment,
so nothing an earlier run left behind can make a later one look successful — and for each finding
checks that the page exists, carries exactly one honesty label, names a version and a tier, links
to evidence that is actually there, and that the program **demonstrates the claim rather than
merely exiting successfully.** Exiting with status zero is not evidence.

It re-derives F01 independently with its own SQL rather than the original author's, because that
was the finding most likely to be an overclaim — and that re-derivation is why F01 is published in
its narrower form. It also lists every database on the node before and after, since F05 is a
finding about orphaned scratch databases and a wave that left more behind while writing it up would
refute itself.

Its output, with the before-and-after database lists and the per-finding verdicts:
[`evidence/upstream/verification.json`](../../evidence/upstream/verification.json).

**Strike count: 1 of 7.** If that number were zero, the right conclusion would not be that we were
right about everything — it would be that the re-check was ceremonial.
