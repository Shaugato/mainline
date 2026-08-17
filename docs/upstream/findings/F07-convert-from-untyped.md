<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# F07 — a call the database cannot resolve is reported under the name of the call that worked

## What happened

We wrote one line of SQL in which one function was called inside another, and we got the inner
call wrong. The database refused it and put the **outer** function's name at the front of the
error message — the outer call was fine — so two attempts went into fixing the wrong thing.

---

**Label: `REPRODUCED-TODAY`.** Re-run 2026-08-17 against a local single-node CockroachDB,
`CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)`.
Transcript: [`evidence/upstream/F07-convert-from-untyped.json`](../../../evidence/upstream/F07-convert-from-untyped.json).
Program: [`scripts/upstream/repro_semantics_and_praise.py`](../../../scripts/upstream/repro_semantics_and_praise.py).

Two words used below, glossed once. A **SQLSTATE** is the five-character code a SQL database
returns with an error; `42883` means *"no function of that name takes those argument types"*. A
**scratch database** is a throwaway database made for one measurement and dropped straight after —
this one was named `upstream_f07_<8 hex characters>`, and the program drops it whatever else
happens, printing both the name it created and the name it dropped.

---

## Where it came from

The original note is in our own tree, written at the time, in the seed file where the statement
lives: [`verticals/mainline/db/seeds/demo/demo_world.sql:843-850`](../../../verticals/mainline/db/seeds/demo/demo_world.sql).
It records the error verbatim:

> `42883 split_part(): unknown signature: convert_from(string, string)`

## What we expected, and what actually happened

`convert_from` turns raw bytes into text. It has exactly one form, and the database will tell you
so:

```sql
SELECT p.proname || '(' || pg_catalog.pg_get_function_arguments(p.oid) || ')'
  FROM pg_proc p WHERE p.proname = 'convert_from';
-- convert_from(bytea, text)
```

Our column `body` holds text, not bytes. Handing text to `convert_from` is therefore our mistake,
and refusing it is correct. **The finding is not that it was refused. The finding is which name
the refusal leads with.**

Called on its own, the message is exactly right:

```
SELECT convert_from(checkpoint.body, 'utf8') FROM checkpoint;
ERROR  42883  unknown signature: convert_from(string, string)
HINT:  No function matches the given name and argument types. You might need to add explicit type casts.
```

Wrap the identical mistake in `split_part`, and the message changes:

```
SELECT split_part(convert_from(checkpoint.body, 'utf8'), chr(10), 3) FROM checkpoint;
ERROR  42883  split_part(): unknown signature: convert_from(string, string) (returning <string>)
```

`split_part` is not the problem. `split_part` is fine. It is the first thing a reader sees.

Nest one level further and the names accumulate, innermost last:

```
SELECT upper(split_part(convert_from(checkpoint.body, 'utf8'), chr(10), 3)) FROM checkpoint;
ERROR  42883  upper(): split_part(): unknown signature: convert_from(string, string) (returning <string>)
```

It is not about these two functions in particular. Swap the outer one, and the outer one is still
what leads:

```
SELECT length(convert_from(checkpoint.body, 'utf8')) FROM checkpoint;
ERROR  42883  length(): unknown signature: convert_from(string, string)
```

Swap the inner one, and the same shape appears:

```
SELECT split_part(encode(checkpoint.body, 'base64'), chr(10), 1) FROM checkpoint;
ERROR  42883  split_part(): unknown signature: encode(string, string) (returning <string>)
```

One more detail, stated only as far as we measured it. The trailing `(returning <string>)` is
present in every message above where `split_part` is the immediate caller, and absent where
`length` is. We did not work out why, and we are not going to guess. What it did to us is the
point: it sits next to a message about `convert_from`, and it reads as a statement about what
`convert_from` returned.

## Why it cost time

The three facts a reader needs are all in that one line, and they are in the wrong order of
prominence. The **name that leads** is the call that resolved. The **name in the middle** is the
call that did not. The **fragment at the end** looks like a claim about the inner call's return
type and is attached to the outer one. We read the line as *"convert_from handed back something
untyped that split_part will not take"*, and started casting the result. The actual fix was to
stop passing text to a function that takes bytes.

The repair, once we were looking at the right call:

```sql
SELECT split_part(convert_from(checkpoint.body::BYTES, 'utf8'), chr(10), 3) FROM checkpoint;  -- 'deadbeef'
```

And what the product actually ships, because `body` was already text and `convert_from` had no
business being there at all
([`demo_world.sql:855`](../../../verticals/mainline/db/seeds/demo/demo_world.sql)):

```sql
split_part(cp.body, chr(10), 3)
```

## How to reproduce it

```
.venv/Scripts/python.exe scripts/upstream/repro_semantics_and_praise.py
```

Thirteen recorded steps against a scratch database that the program creates and drops. It prints
both the name it created and the name it dropped, and reports how many databases it left behind —
a number that must be zero.

## Where we were wrong

**Most of this one is ours, and it is worth saying twice.** Passing a text column to a function
that takes bytes is our error. The database refused it, returned the right SQLSTATE, and printed
a hint telling us to add an explicit cast. A reader who wants to dismiss this finding as "they
wrote bad SQL and blamed the error message" is half right, and the half they are right about is
the half we caused.

Two further things we were wrong about, both of which we believed until we measured them today,
and both of which we now **withdraw**:

1. **"`convert_from` returns an untyped `<string>` that `split_part` will not resolve without an
   explicit `::STRING`."** It does not. Applied to a genuine bytes column, `convert_from` reports
   its return type as `text`, and `split_part` accepts it with no cast anywhere in the statement.
   Measured today, steps 13 and 14 of the transcript. This claim came from reading
   `(returning <string>)` as a fact about `convert_from`, and it is not one.

2. **"The same statement resolved on a local single-node cluster while failing `42883` on Cloud
   Basic."** Not a difference between the two, as far as we can now show. On this one node, today,
   at one version, the statement fails on a text column and resolves on a bytes column. The thing
   that changed between our two original runs was the column type, not the cluster — and our own
   comment says so four lines further down
   ([`demo_world.sql:848-850`](../../../verticals/mainline/db/seeds/demo/demo_world.sql)): *"a
   scratch table written from memory made the same mistake and the repair PASSED against it —
   which is a test proving a statement against a schema the product does not have."*

   **The Cloud Basic half was not re-run today.** Running this statement there means creating
   tables and loading rows on a cluster other people are using, which the plan for this document
   set forbids for exactly that reason. So the Cloud observation stands as a note in a file from
   the day it happened and nothing more; this document does not claim it was measured today, and
   the label at the top of this file covers only the attribution behaviour reproduced above. Both
   withdrawn claims are reported to
   [`docs/upstream/STRIKE-LEDGER.md`](../STRIKE-LEDGER.md).

## What better would look like

**Lead with the call that failed, and name the callers after it.** The information is already all
there — only the order is wrong:

```
ERROR  42883  unknown signature: convert_from(string, string)
              in argument 1 of split_part()
HINT:  No function matches the given name and argument types. You might need to add explicit type casts.
```

That is the same line count and the same content. The first thing the reader sees is the name they
need to go and look at. If the current order has to stay for compatibility, the argument position
alone would do most of the work: `split_part(): argument 1: unknown signature: convert_from(string,
string)` puts a pointer in front of the reader that the current message leaves them to infer.
