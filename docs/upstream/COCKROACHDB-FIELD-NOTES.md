<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Field notes from building on CockroachDB

*Six things we hit while building a real system on CockroachDB over several weeks, written down
the way you would write them for a colleague. Every one of them has a program you can run.*

---

## Sixty seconds, no jargon

Here is the sharpest thing we found. There is nothing in it you need to look up.

> We took away one test user's permission to run one small program that lives inside the database.
> The database then refused to let that user run it, exactly as it should.
>
> But when we asked the database — same session, same user, same program — *"is this user allowed
> to run it?"*, the database answered **yes**.
>
> We had a safety check in our own code that asked the database that question. It could never
> have caught anything.

That is finding F01 below. The other five are smaller, and all six are the same shape: something
behaved differently from what we expected, we lost hours to the difference, and the difference is
worth a maintainer knowing about.

**We are not a research team filing bugs.** We picked this database, built a product on it, and
these are the edges we hit on the way. The product's whole claim is that *the database itself*
refuses work that contradicts a recorded decision — the refusal is a rule inside the table, not a
check in application code. That design means the database's exact behaviour mattered to us more
than it does to most applications, which is why we noticed some of these at all.

### Before the complaints: three things that worked

A critique with no praise is a grievance. Three things about this database carried the product,
and they are measured with the same programs and the same standard as everything below:

**→ [What worked — three things that carried this product](WHAT-WORKED.md)**

Briefly: rules written into the table refuse bad writes with no application in the path; the
strongest safety setting for concurrent work is already on before anyone configures anything; and
the error codes are exact enough that we put them on screen as evidence.

### We threw one out

**We struck 1 finding of 7.** We started with seven candidates, re-ran every one of them from
scratch before publishing, and one did not survive. We had written down — and published in our own
README — that when answering one particular kind of search, CockroachDB would not take a shortcut
we had built for it unless we named that shortcut in the query. We tried to show that twice. Both
times the database took the shortcut without being asked. The claim was wrong, so we withdrew it.

Six further individual sentences were withdrawn from *inside* the six findings that did survive.
Both counts, and what we saw instead in each case, are in
**[the strike ledger](STRIKE-LEDGER.md)**.

We would rather publish six things a reader can check than seven with one we cannot demonstrate.

---

## Words this page uses

Each of these appears below, or on a page linked from here. None of them appears before this list.

| Word | What it means here |
|---|---|
| **index** | A second copy of some of a table's data, arranged so that one particular question can be answered without reading the whole table. |
| **SQLSTATE** | The five-character code a database attaches to an error, so a program can recognise a specific failure without reading English. `42501` means *"you do not have permission"*. Codes are stable across versions, which is why we quote codes rather than message text. |
| **routine** | A chunk of SQL stored inside the database under a name — a stored procedure or function. Applications run it by name instead of sending the SQL themselves. |
| **catalogue** | The tables a database keeps *about itself*: what exists, who owns it, who may use it. You read it with ordinary SQL. |
| **query plan** (or **optimizer plan**) | The database's written-out decision about *how* it will answer a question — which indexes it reads, in what order. You ask for it by writing `EXPLAIN` in front of a query. |
| **CHECK constraint** | A rule written into a table's own definition. The database refuses any row that breaks it, whoever is writing and however they got there. |
| **trigger** | A small program stored inside the database that the database itself runs when a row changes. No application calls it, and no application can decline to. |
| **scratch database** | A throwaway database created for one measurement and dropped straight after. Ours are named `upstream_f<NN>_<8 hex characters>`. |
| **tier** | Which hosting plan a measurement was taken on. CockroachDB Cloud **Basic** is the free plan; a **local single-node** cluster is one copy of the database on one machine where you are the administrator. **These are two different exams**, and a result on one is never claimed for the other. |
| **zone configuration** | A small bundle of storage settings attached to a database, a table, or the whole cluster. Objects with none of their own inherit from a cluster-wide fallback called `RANGE default`. |
| **GC TTL** (`gc.ttlseconds`) | When you update or delete a row, the database keeps the old version for a while before garbage-collecting it. This setting is how many seconds "a while" is, and so how far into the past you can read. `4500` is 75 minutes. |
| **SERIALIZABLE** | The strongest isolation setting: transactions running at the same time are guaranteed to come out as if they had run one after another, in some order. |
| **ANN** | *Approximate nearest neighbour* — a "find me the rows most similar to this one" search, as opposed to "find me the row with this id". *Approximate* because it is allowed to miss a near-match in exchange for speed. It appears here only in the strike ledger, because the finding that used it did not survive. |

---

## The six findings

All six were measured on **CockroachDB CCL v26.2.5** (`x86_64-pc-linux-gnu`, built
2026/07/28 18:56:00). The **label** column says how each was verified:

- **`REPRODUCED-TODAY`** — re-run on 2026-08-17 against a local single-node cluster, with the
  transcript written to `evidence/upstream/`.
- **`ARCHIVED-EVIDENCE`** — measured on a stated earlier date and **not re-run today**, because
  re-running it would mean mutating something shared or expensive. The finding says so plainly.

| # | What goes wrong, in one line | SQLSTATE | Tier it was measured on | Label |
|---|---|---|---|---|
| **[F01](findings/F01-has-function-privilege.md)** | Asked whether a *named* user may run a routine, the database answers `true` even after that user's permission was revoked and the engine itself refuses the call. A check built on **that** form cannot fail — and it is the form a checking program has to use, because it asks about somebody other than itself. The other form, where a user asks about *itself*, answers correctly. | engine refuses with `42501`; the question itself returns no error, just the wrong answer | local single-node CCL | `REPRODUCED-TODAY` |
| **[F02](findings/F02-show-grants-signature.md)** | Two catalogue surfaces spell one routine two different ways — `SHOW GRANTS` gives the full argument list, `information_schema.routines` gives the bare name — and neither carries the other's spelling. Comparing them as plain text, which is what we did, produces false alarms forever. | none — a wrong answer, not an error | local single-node CCL | `REPRODUCED-TODAY` |
| **[F04](findings/F04-crdb-internal-restricted.md)** | The `crdb_internal` and `system` bookkeeping tables are closed by default. The refusal names a session setting that reopens them and describes it as *not recommended*, but never names the supported alternative that would actually answer the question. | `42501` | local single-node CCL (today) **and** Cloud Basic, `aws-ap-southeast-1` (archived, 2026-08-11) — labelled separately, never merged | `REPRODUCED-TODAY` (local) · `ARCHIVED-EVIDENCE` (Cloud) |
| **[F05](findings/F05-schema-object-cap.md)** | A cluster may hold about 20,000 schema objects. The refusal when you reach it is excellent. Getting there is the problem: nothing counts down, no warning is emitted on the way up, and the count that would tell you where you stand lives in the schema F04 closes. It arrived as thirteen broken tests. | `53400`, reported by the driver as `ConfigurationLimitExceeded` | local single-node CCL | `ARCHIVED-EVIDENCE` |
| **[F06](findings/F06-gc-ttlseconds.md)** | `SHOW ZONE CONFIGURATION` returns the same number whether a setting is inherited from the cluster default or was set by you; only a separate column says which. We read our own value back as the platform's, and published it. Separately, reading further back than the window allows fails with a message that never names the setting you must change. | `XXUUU` — the code used when no more specific one applies | local single-node CCL | `REPRODUCED-TODAY` |
| **[F07](findings/F07-convert-from-untyped.md)** | When one function call is nested inside another and the *inner* one cannot be resolved, the error message leads with the *outer* function's name — the call that was fine. Two attempts went into fixing the wrong function. | `42883` | local single-node CCL | `REPRODUCED-TODAY` |

**F03 is missing from that list on purpose.** It was struck. It is in
[the strike ledger](STRIKE-LEDGER.md) with the plan output that refutes it.

Each finding file has the same five parts: what happened in two sentences of plain language; the
mechanism; the transcript; **where we were wrong**; and **what better would look like** — one
concrete, implementable change rather than a wish. Two of the six are mostly our own mistakes and
say so in their first paragraph.

---

## How to check any of this

Nothing here asks to be taken on trust. Each finding names the program that produces it:

```
.venv/Scripts/python.exe scripts/upstream/repro_privileges.py             # F01, F02
.venv/Scripts/python.exe scripts/upstream/repro_vector_and_catalogue.py   # F04 (and struck F03)
.venv/Scripts/python.exe scripts/upstream/repro_limits.py                 # F05, F06
.venv/Scripts/python.exe scripts/upstream/repro_semantics_and_praise.py   # F07, and what worked
```

Each program creates one scratch database, prints the name it created and the name it dropped,
drops it in a `finally` block so it goes even on the error path, and reports how many databases it
left behind — a number that must be zero. None of them touches a CockroachDB Cloud cluster, makes
an AWS call, or prints a credential.

And to check all of them at once, including us:

```
.venv/Scripts/python.exe scripts/upstream/verify_field_notes.py
```

That program was written by someone who wrote none of the findings, and its purpose is to strike
them. It re-runs all four programs from a cold shell — a fresh process with a clean environment,
so nothing an earlier run left behind can make a later one look successful — and for each finding
it checks that the page exists, carries exactly one label, names a version and a tier, links to
evidence that is actually there, and that the program **demonstrates the claim rather than merely
exiting successfully**. Exiting with status zero is not evidence.

It re-derives F01 independently with its own SQL rather than the original author's, because that
was the finding most likely to be an overclaim — and the re-derivation is the reason F01 is
published in its narrower form. It also lists every database on the node before and after, since
F05 is a finding about orphaned scratch databases and a wave that left more behind while writing
it up would refute itself.

Its output, including the before-and-after database lists and the per-finding verdicts:
[`evidence/upstream/verification.json`](../../evidence/upstream/verification.json).

---

## What we are not claiming

- **No finding here was measured on CockroachDB Cloud today.** Where a Cloud reading exists it is
  an archived artefact from a stated earlier date, labelled `ARCHIVED-EVIDENCE`, and it is not
  presented as a fresh measurement.
- **A result on one tier is not claimed for another.** F04 is the only finding measured on both,
  and its two arms are labelled and reported separately.
- **We did not read CockroachDB's source.** These are behaviours with programs attached, not
  diagnoses. Where we cannot explain a cause we say we cannot.
- **We are not filing severity ratings.** None of this is a security report and none of it is
  presented as one.
- **None of this has been sent to Cockroach Labs yet.** This document set is the thing we would
  send.

---

## Read next

- **[WHAT-WORKED.md](WHAT-WORKED.md)** — the three platform features the product could not exist
  without, measured the same way.
- **[STRIKE-LEDGER.md](STRIKE-LEDGER.md)** — the finding we struck, the six sentences we withdrew,
  and the judge-facing documents that still carry one of them.
- **[findings/](findings/)** — one file per finding, with the full transcript and the exact
  statements.
