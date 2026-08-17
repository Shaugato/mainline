<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# F05 — the limit on how many tables you may have, met as thirteen broken tests

## What happened

Our test suite went from all-green to thirteen broken tests overnight, and for most of an hour it
looked as though somebody's code change had broken it. Nothing had — the database had quietly run
out of room for new tables, because we had spent weeks making throwaway copies of our database for
tests and never deleting them afterwards.

That is the whole finding. The mess was ours. What we are sending upstream is the shape of how we
found out.

---

## Label, version and which machine this was measured on

**Label: `ARCHIVED-EVIDENCE`.** The failure was recorded twice — **2026-08-16** and again earlier on
**2026-08-17** — both times on our **local single-node CockroachDB CCL v26.2.5** (built 2026/07/28
18:56:00). The node has since been swept and now sits at 19.4 % of the ceiling, so **the refusal
itself was not re-triggered for this note and could not honestly be**: re-triggering it means
creating twenty thousand schema objects on purpose, and this finding is *about* leaving twenty
thousand schema objects lying around. Everything measurable without doing that **was** re-measured
today, read-only, and is marked in place as it appears.

**Not measured on CockroachDB Cloud.** Nothing in this note is a statement about a Cloud cluster
or about any hosting tier. *(A **tier** is the plan you buy — Basic, Standard, Advanced. Different
tiers get different limits, so a limit measured on one is not a limit claimed for another.)*

---

## Words this note uses

* **Schema object** — a thing the database keeps in its own bookkeeping: a table, a view, a
  sequence, a schema, a database, a user-defined function. Not a *row*. A database with a million
  rows in ten tables holds ten-ish schema objects, not a million.
* **Catalogue** — the database's list of its own schema objects, readable as ordinary tables
  (`information_schema.tables` and friends). You query the catalogue to ask the database what it
  contains.
* **Scratch database** — a throwaway database a test creates so it can build tables freely without
  disturbing anything real. Ours are called things like `w_w6` and `w1_credentials_9c1ec080bd16`.
  A scratch database is supposed to be dropped when the test finishes.
* **SQLSTATE** — the five-character code a SQL error carries alongside its English message, e.g.
  `42501`. Programs branch on the code; humans read the message.

---

## The ceiling, and the mechanism

CockroachDB caps the number of schema objects a cluster may hold. The cap is a cluster setting,
and on our node it reads:

```
$ SHOW CLUSTER SETTING sql.schema.approx_max_object_count
20000
```

A test database that holds a full copy of our product schema costs about **146** schema objects —
measured today, read-only, the ten heaviest databases on this node run 144 to 146 apiece.
**Roughly 137 full copies fill the cluster.** When the ceiling was met there were **242** databases
holding **20,270** objects between them, an average of about 84 each, so a mixture of full and
partial copies got there first. *(242 databases, 54 of them scratch-shaped:
`docs/demo/film/CLAIMS-CLEARANCE.md:2213`.)*

When the cap is reached, every `CREATE` fails. This is what it said, quoted from the JUnit XML of
the run rather than off a terminal:

```
psycopg.errors.ConfigurationLimitExceeded: error executing StatementPhase stage 1 of 1 with
17 MutationType ops: cannot create new schema object(s): would exceed approximate maximum
(20000); current count: 20270
HINT:  You can increase the limit by adjusting the cluster setting sql.schema.approx_max_object_count
```

*Source: `docs/demo/film/CLAIMS-CLEARANCE.md:2152`, run of 2026-08-16. The same refusal at
`current count: 20161` in `docs/submission/EXTRA-CREDIT-CLAIMS.md:362-367`, and at
`current count: 19999` in `docs/submission/PRESHOOT-VERDICT.md:289`. Three different counts because
it was hit three times as the number drifted.*

---

## What is good here, and we want to say it first

**The message is excellent.** It states the maximum, states the current count, and names the exact
cluster setting you would change. There is nothing to fix about the sentence.

**We are correcting our own brief on this point.** This finding was handed to us worded as *"the
cap surfaces as unrelated failures rather than as a quota error a reader can act on."* The second
half of that is **wrong and is not published**: it *is* a quota error and a reader *can* act on it.
An earlier pass over the same material reached the same conclusion independently and dropped the
overstated wording — `docs/submission/readme-parts/05-findings.claims.md:31`.

---

## What actually cost the time: where the message arrives

The message is fine. The **place** it appears is the problem.

Every one of the thirteen failures happened in *fixture setup* — the preparation step a test runs
before its own code, which is where the scratch database gets created. So the test framework
attributed each failure to the test whose setup it was:

| run | collected | passed | failed | errors | skipped |
|---|---|---|---|---|---|
| baseline | 1070 | 1069 | 0 | 0 | 1 |
| the saturated node | 1070 | **1056** | **1** | **12** | 1 |

*Source: `docs/demo/film/CLAIMS-CLEARANCE.md:2152` (2026-08-16), and independently
`docs/submission/PRESHOOT-VERDICT.md:275-289` (2026-08-17).*

What a reader sees at the top of the report is thirteen named tests — `test_judge_can_sign.py`
twelve times, `test_reads.py` once — in files nobody had touched. The quota message is inside each
test's traceback rather than in the summary. So the first hypothesis is *"the change we just made
broke the suite"*, and the work that follows is proving a code change innocent: checking that the
collected count did not move, that the changed files were all Markdown, that both suite paths were
byte-identical to the last commit. All of that was real work, and none of it was the answer.

**Nothing counts down towards the ceiling.** Reproduced today, read-only:

* Creating a database on a node at **19.4 %** of the ceiling emitted **0** notices from the server.
  There is no threshold at which anything says *"you are getting close."*
* There is no supported way to ask how many schema objects you have. The internal view that knows
  is refused:

  ```
  $ SELECT count(*) FROM crdb_internal.tables
  ERROR (42501): Access to crdb_internal and system is restricted.
  HINT: These interfaces are unsupported in production. To proceed, set the session variable
        allow_unsafe_internals = true (not recommended), or contact Cockroach Labs for a
        supported alternative.
  ```

* So we counted by hand, out of the catalogue, one database at a time: **3,876** objects across
  **37** databases today, of which **33** are scratch-shaped leftovers. That number is an
  **approximation and is labelled as one in the artefact** — the server counts internal
  descriptors, we counted catalogue rows, and user-defined types are not in our total. A team
  cannot manage a budget it can only estimate. *(The census counts catalogue rows in every database
  on the node, our real one included. It reads no table data and writes nothing.)*

The combination is what stings: the ceiling is enforced, announced only on impact, and not readable
in advance without an interface the server tells you not to use.

---

## Where we were wrong

Nearly all of it.

1. **We created the databases.** Every test wave spun up scratch databases and did not drop them.
   Our own leftovers were the entire cause, and the node has not been fully swept since: thirty-three
   of them are still there as of `evidence/upstream/F05-schema-object-cap.json` (2026-08-17), by
   name `w_w6`, `w_w7`, `w_w7_borrow`, `w_w4stab_shared`, `w_w5_order_w1`,
   `w1_credentials_9c1ec080bd16` and twenty-seven more.
2. **Our fixtures had no teardown.** The fix is ours to make and is not a CockroachDB change.
3. **We spent the first hour on the wrong hypothesis** and could have spent none of it, had we
   read the traceback before reading the summary.
4. **The briefed wording of this finding overstated it**, and we are publishing the correction
   above rather than the brief.
5. **This note's own reproduction script exists because of this finding.**
   `scripts/upstream/repro_limits.py` creates exactly one database, names it `upstream_f05_<8 hex>`,
   prints the `CREATE` and the `DROP`, and drops it from a `finally:` block so it goes away on the
   error path too. Documenting a mess caused by orphaned databases while leaving one behind would
   be self-refuting.
6. **The classification "scratch-shaped" is a heuristic**, here and in the archived readings: it is
   every database that is not `defaultdb`, `postgres`, `system` or our one real database. It is not
   a fact the server reports.

---

## Reproducing what can be reproduced

```
$ .venv/Scripts/python.exe scripts/upstream/repro_limits.py
```

Read-only apart from one scratch database it drops. Green output on 2026-08-17 (UTC):

```
node   CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
exam   local single-node CockroachDB, NOT CockroachDB Cloud

F05  ceiling            20000 (sql.schema.approx_max_object_count)
F05  databases          37, of which 33 are scratch-shaped
F05  counted objects    3876 (approximate), 19.4% of the ceiling
F05  headroom           16124
F05  crdb_internal      refused 42501
F05  CREATE upstream_f05_67f48e0e  ok, 0 notice(s) from the server
...
F05  DROP upstream_f05_67f48e0e  done - this script leaves no database behind
OK  every load-bearing probe answered
```

Full transcript: **`evidence/upstream/F05-schema-object-cap.json`**.

What it does **not** do: manufacture 20,000 objects to re-trigger the refusal. The refusal itself
stays `ARCHIVED-EVIDENCE`, cited above to three separate documents that recorded it at the time.

---

## What better would look like

**Emit a `NOTICE` on schema-creating statements once the object count crosses a fraction of the
ceiling** — say 80 %, with the fraction itself a cluster setting so a team can turn it off. The
counting machinery already exists: the `CREATE` path computes the current count in order to refuse,
so the same number is available on the statements that succeed. A team that saw something like
`NOTICE: 16,412 of 20,000 schema objects used` — our wording, not a real message — once a week
would have dropped its leftovers in minutes instead of meeting the ceiling in a red test report.

The cheaper half of the same idea, if the notice is unwelcome: **make the count readable without
`crdb_internal`.** A single supported row — `SHOW SCHEMA OBJECT COUNT`, or a column beside the
cluster setting — would let anyone build the alert themselves. Today the only honest answer to
*"how close am I?"* is a hand-rolled sum across every database that the server itself would not
agree with.


*Measured against CockroachDB CCL **v26.2.5** (built 2026/07/28 18:56:00), **local single-node**,
over `postgresql://root@localhost:26257/defaultdb?sslmode=disable`. Not a Cloud measurement and not
a claim about any hosting tier. Reproduction: `scripts/upstream/repro_limits.py`. Transcript:
`evidence/upstream/F05-schema-object-cap.json`.*
