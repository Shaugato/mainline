<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# F06 — how far back you can read, and how we got the number's origin wrong

## What happened

CockroachDB lets you read your data as it looked a while ago, and a setting decides how far back
"a while" reaches. We wrote in several of our own documents that CockroachDB's cheapest cloud plan
sets that dial to 75 minutes *by default* — and we cannot back that up, because the tool that read
the number had just set that same number itself, and it discarded the part of the answer that says
where a value came from.

---

## Label, version and which machine this was measured on

**Label: `REPRODUCED-TODAY`.** Every measurement below was taken on **2026-08-17 (UTC)** against
our **local single-node CockroachDB CCL v26.2.5** (built 2026/07/28 18:56:00), over
`postgresql://root@localhost:26257/defaultdb?sslmode=disable`. Transcript:
`evidence/upstream/F06-gc-ttlseconds.json`.

**One sentence is struck before anything else.** We had a finding drafted that read
*"`gc.ttlseconds` **defaults** to 4500 on CockroachDB Cloud Basic."* **We cannot support it and it
does not appear as a claim anywhere in this note.** What replaces it is what we actually measured,
which turned out to be more interesting and considerably more embarrassing.

---

## Words this note uses

* **`gc.ttlseconds` / GC TTL** — when you update or delete a row, CockroachDB keeps the old version
  around for a while before garbage-collecting it. `gc.ttlseconds` is how many seconds "a while" is.
  It is measured in seconds: 4500 is 75 minutes; 14400 is 4 hours.
* **`AS OF SYSTEM TIME`** — the SQL that reads the database as it was at some past instant, e.g.
  `SELECT … FROM t AS OF SYSTEM TIME '-1h'`. It works only as far back as `gc.ttlseconds` allows,
  because past that point the old versions have been thrown away.
* **Zone configuration** — a small bundle of storage settings (`gc.ttlseconds` among them) attached
  to a database, a table, or the whole cluster. Objects that have none of their own inherit from a
  cluster-wide fallback called `RANGE default`.
* **`SHOW ZONE CONFIGURATION`** — the statement that reads one back. It returns **two** columns: a
  **target**, naming the object the settings actually belong to, and the settings themselves,
  rendered as a runnable `ALTER … CONFIGURE ZONE USING …` statement.
* **SQLSTATE** — the five-character code attached to a SQL error, e.g. `3D000`. Programs branch on
  the code; humans read the message.
* **Tier** — the plan you buy on CockroachDB Cloud: Basic, Standard, Advanced. Limits differ
  between them, so a number measured on one is not a number claimed for another.
* **Scratch database** — a throwaway database created for one measurement and dropped afterwards.

---

## First half, reproduced today: a value that does not say where it came from

Three statements, in order, on a database created seconds earlier and configured by nobody.

```
$ SHOW ZONE CONFIGURATION FOR RANGE default
target: RANGE default
        ALTER RANGE default CONFIGURE ZONE USING
                ...
                gc.ttlseconds = 4500,
                ...

$ CREATE DATABASE upstream_f05_67f48e0e
$ SHOW ZONE CONFIGURATION FOR DATABASE upstream_f05_67f48e0e
target: RANGE default                       <-- inherited; this database has none of its own
        ALTER RANGE default CONFIGURE ZONE USING
                gc.ttlseconds = 4500,

$ ALTER DATABASE upstream_f05_67f48e0e CONFIGURE ZONE USING gc.ttlseconds = 4500
$ SHOW ZONE CONFIGURATION FOR DATABASE upstream_f05_67f48e0e
target: DATABASE upstream_f05_67f48e0e      <-- now it has one of its own
        ALTER DATABASE upstream_f05_67f48e0e CONFIGURE ZONE USING
                gc.ttlseconds = 4500,
```

**The number is 4500 in both states.** The only thing separating *"the platform handed me this"*
from *"we set this"* is the target — and the rendered statement's first line, which likewise says
`RANGE default` when nothing was configured.

Our deployment tool kept neither. `scripts/deploy/cloud_chain.py:1029` lifts the value out with a
regular expression and throws away the rest:

```python
match = re.search(r"gc\.ttlseconds\s*=\s*(\d+)", str(row[1]))
```

`row[1]` is the settings column. `row[0]` — the target — is never read. The reproduction script
runs that exact expression against both readings above and gets **4500** from each; the artefact
records `values_are_identical: true` beside `targets_are_identical: false`. Downstream, the
artefact `evidence/deploy/cloud-chain.json` records the whole thing as
`{"requested": 4500, "accepted": true, "observed": 4500}` — a request being honoured, with no trace
of what the value would have been had nobody asked.

**CockroachDB disclosed the provenance twice and we read neither disclosure.** That is the honest
summary, and it is why the upstream ask at the bottom of this note is a small one.

---

## Second half, reproduced today: neither failure mentions the setting

There are two ways a time-travel read fails, and we hit both today.

**Reading before the object existed.** On the scratch database created moments earlier:

```
$ SELECT count(*) FROM "upstream_f05_67f48e0e".public.t AS OF SYSTEM TIME '-30s'
ERROR (3D000): database "upstream_f05_67f48e0e" does not exist
```

Correct, and correctly refused rather than silently answering from an empty past.

**Reading past the retention window.** This needs a table older than the window, so the script
finds one — any leftover test database will do, read only, and it records which one it used. On
this run it was `w1_credentials_9c1ec080bd16`, one of the orphans F05 is about:

```
$ SELECT count(*) FROM "w1_credentials_9c1ec080bd16"."mainline"."activity_node"
      AS OF SYSTEM TIME '-1h'                                              -> 0 rows, OK
$ SELECT count(*) FROM "w1_credentials_9c1ec080bd16"."mainline"."activity_node"
      AS OF SYSTEM TIME '-2h'
ERROR (XXUUU): batch timestamp 1786978495.862868698,0 must be after replica
               GC threshold 1786981181.723324325,0 (r9533: /{Table/1248-Max})
```

`-1h` is inside the window and answers. `-2h` is outside it and is refused. Any table older than
75 minutes shows the same pair; if a node has none, the script records the probe as unavailable
rather than inventing a result.

Four things about that message, all checkable in the transcript:

1. **It never says `gc.ttlseconds`,** which is the one thing the reader must change.
2. **It never names the table or the database.** It names a range id, `r9533`, and a key span.
3. **The SQLSTATE is `XXUUU`** — the code CockroachDB uses when no more specific one applies. This
   is not an unexpected condition; it is the configured limit doing exactly its job. A caller that
   wants to catch *"too far back, retry closer to now"* has nothing stable to catch.
4. **The window is recoverable from the message, but only by arithmetic.** The two timestamps are
   the instant you asked for and the oldest instant still kept, so
   `requested_offset - (threshold - batch_timestamp)` gives the window in force. Done at -2h, -5h
   and -24h it yields **4514.1 s** every time: the same answer three ways. That is about fourteen
   seconds *more* than the configured 4500, because the threshold only advances when collection
   actually runs — earlier runs of the same probe derived 4505.9 s and 4534.9 s. A satisfying
   consistency check, and a strange way to have to learn your own setting.

*The scratch database's name is eight random hex characters, generated per run, so a re-run of the
script will print a different one than the transcript quoted here. Everything else above should
match.*

---

## What we can say about CockroachDB Cloud — archived, not re-run

Nothing in the section above is a Cloud measurement, and this note issues no statement against any
Cloud cluster. What the committed record supports, and no more:

| Date | Where | What was recorded |
|---|---|---|
| 2026-08-07 | Basic tier, `aws-ap-southeast-1` | `gc.ttlseconds` read as **4500** — `docs/adr/0002-g1-platform-ground-truth.md:22` (GT-07). The ADR states the value in a summary row; **no artefact under `evidence/` records the statement, its target, or whether the database had been configured** |
| 2026-08-10 | same cluster, `mainline_demo` | `{"requested": 4500, "accepted": true, "observed": 4500}` — `evidence/deploy/cloud-chain.json` → `zone`. A request being honoured |

So the supportable statement is:

> **The retention window in force on our CockroachDB Cloud Basic database was 4500 seconds —
> 75 minutes — where our own architecture had assumed 14400 (4 hours). Every design of ours that
> reaches into the past was re-scoped around roughly one hour as a result. Whether 4500 was the
> tier's own default or a value someone had set, we do not know, because no artefact we hold
> recorded the target.**

That re-scoping was real and is recorded at `docs/adr/0002-g1-platform-ground-truth.md:52`: all
long-horizon history moved to an application-level structure, and no demo beat may depend on
`AS OF SYSTEM TIME` reaching further than about an hour.

**And the number moved on our own laptop, which should have warned us.** `qa/test-state.json`
records `gc_ttlseconds: 14400` on this same local node. Today it reads **4500** — because our own
`just gc-align` runs `ALTER RANGE default CONFIGURE ZONE USING gc.ttlseconds = 4500`
(`scripts/qa/doctor.py:980`) so that a time-travel assumption which passes locally cannot fail on
Cloud. The number is not a property of a platform. It is a property of whoever ran what, last.

---

## Where we were wrong

Essentially all of it.

1. **"Defaults to 4500 on Basic" was never measured.** It is an inference from one number with its
   provenance missing, and it is struck.
2. **We wrote the tool that lost the provenance.** The regex at `cloud_chain.py:1029` is not wrong;
   discarding `row[0]` is.
3. **CockroachDB told us anyway** — in the target column and in the first line of the rendered
   statement — and our artefact preserved neither. A platform is not at fault for an answer we did
   not store.
4. **The claim spread.** Line numbers as read on 2026-08-17: `docs/deploy/CLOUD-40001.md:75` prints
   `4500` in the Cloud column against `14400` in the local column, which reads as a tier difference
   and is not evidenced as one. `docs/deploy/unproduced-tables.md:249` calls 4500 *"the value Cloud
   Basic enforces"*. `README.md:258` says the same — **and "enforces" is stronger again than
   "defaults to"**, since our own artefact shows a `CONFIGURE ZONE` being *accepted* on that
   cluster, which is the opposite of enforcement. This wave's rules forbid us to edit `README.md`,
   so that line is **flagged, not fixed**, and handed to the document leads with this note.
5. **An earlier pass reached the same conclusion before us** and dropped the claim on the same
   grounds — `docs/submission/readme-parts/05-findings.claims.md:30`. We re-derived it rather than
   inheriting it, which is the right process, but the sentence had already been caught.
6. **We could have settled it for good and did not.** Reading `SHOW ZONE CONFIGURATION` on a Cloud
   Basic database nobody had configured, keeping both columns, would answer the question in one
   statement. We are not doing it in this wave: it would mean issuing statements against a live
   deployment we have frozen, and a finding is not worth breaking a freeze for.

---

## Reproducing this

```
$ .venv/Scripts/python.exe scripts/upstream/repro_limits.py
```

Read-only against the local node apart from one scratch database, named `upstream_f05_<8 hex>`,
whose `CREATE` and `DROP` are both printed and whose `DROP` runs from a `finally:` block. The one
`CONFIGURE ZONE` in the script is issued against that scratch database and nothing else. Green
output on 2026-08-17 (UTC):

```
F06  RANGE default      gc.ttlseconds = 4500
F06  fresh database     gc.ttlseconds = 4500, target = 'RANGE default' (nobody configured this database)
F06  after our pin      gc.ttlseconds = 4500, target = 'DATABASE upstream_f05_67f48e0e'
F06  new-object AOST    -30s -> 3D000, -2h -> 3D000, -5h -> 3D000
F06  retention refusal  ['XXUUU'] | names gc.ttlseconds: False | names the table: False |
                        window derived from the message: 4514.1 s at -2h, -5h and -24h alike
OK  every load-bearing probe answered
```

The script exits non-zero if the inherited and the explicit reading ever stop agreeing on the
number, or stop differing in their target — that is, if the claim above stops holding on the node
it is run against. A finding whose own script cannot still demonstrate it should not ship.

---

## What better would look like

**One.** When `SHOW ZONE CONFIGURATION FOR DATABASE x` is answered by inheritance, the settings
column renders `ALTER RANGE default CONFIGURE ZONE USING …` — a statement which, copied out and
run, changes a cluster-wide default rather than that database. A single comment line at the head of
the rendering would remove the hazard and carry the provenance into every screenshot, paste and
regular expression that follows it:

```
-- DATABASE x has no zone configuration of its own; these settings apply via RANGE default
ALTER RANGE default CONFIGURE ZONE USING
        gc.ttlseconds = 4500,
        ...
```

We would not have written the struck sentence had that line been in front of us.

**Two.** Give the retention refusal a stable, specific SQLSTATE outside the catch-all class, and
name the setting in the text — *"… exceeds the 4500 s retention window (`gc.ttlseconds`) for
`db.schema.table`"*. Both numbers are already in the message; the sentence just doesn't spend them
on the reader. Running past your history window is an ordinary, expected, configured outcome, and
it is the one error in this whole build that we could not catch by its code.


*Measured against CockroachDB CCL **v26.2.5** (built 2026/07/28 18:56:00), **local single-node**.
The Cloud rows are **archived evidence from 2026-08-07 and 2026-08-10, not re-run**, and are
labelled as such in place. Reproduction: `scripts/upstream/repro_limits.py`. Transcript:
`evidence/upstream/F06-gc-ttlseconds.json`.*
