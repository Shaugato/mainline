<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# What worked — three things about CockroachDB that carried this product

Three things this database does made the difference between a product and a plan, and we would
like to say so before we say anything else. Each one below is checked the same way the complaints
are: a file and a line you can open, and where it is possible, a program you can run that shows
the database doing it.

**Label: `REPRODUCED-TODAY`.** All three re-measured 2026-08-17 against a local single-node
CockroachDB, `CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00,
go1.25.5)`. Transcript:
[`evidence/upstream/WHAT-WORKED.json`](../../evidence/upstream/WHAT-WORKED.json). Program:
[`scripts/upstream/repro_semantics_and_praise.py`](../../scripts/upstream/repro_semantics_and_praise.py).

```
.venv/Scripts/python.exe scripts/upstream/repro_semantics_and_praise.py
```

Words used below, each glossed once. A **CHECK constraint** is a rule written into a table's own
definition; the database refuses any row that breaks it, whoever is writing and however they got
there. A **trigger** is a small program stored inside the database that the database itself runs
when a row changes — no application calls it, and no application can decline to. A **SQLSTATE** is
the five-character code a SQL database returns with an error. **Isolation** is the rule for what
two transactions running at the same moment are allowed to see of each other, and **SERIALIZABLE**
is the strongest setting of it: they are guaranteed to come out as if they had run one after the
other, in some order. A **scratch database** is a throwaway database made for one measurement and
dropped
straight after. A **tier** is which hosting plan a measurement was taken on — a local single-node
cluster and CockroachDB Cloud Basic are two different exams, and a result on one is not claimed
for the other.

---

## 1. The refusal is the table's, not the application's

**Plainly.** Our whole product is one sentence: *a job that ignores a recorded lesson is refused
by the database itself.* If the refusal lived in application code, it would be a policy that a
second application, a migration script, or somebody with a SQL prompt could walk straight past.
Because CockroachDB carries both named `CHECK` constraints and triggers written in the database's
own procedural language, the refusal lives in the table, and there is no path that avoids it.

**Where it is in this repository.**

| Mechanism | File and line |
|---|---|
| the rule on the permit | `CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0)` — [`verticals/mainline/db/migrations/0050_permit.sql:114`](../../verticals/mainline/db/migrations/0050_permit.sql) |
| the rule on the change request | `CONSTRAINT cr_gate_closed_when_merged` — [`verticals/mainline/db/migrations/0051_change_request.sql:85`](../../verticals/mainline/db/migrations/0051_change_request.sql) |
| the stored program that recounts | [`verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:44`](../../verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql) |
| the weld to the table, with its `WHEN` clause | [`verticals/mainline/db/migrations/0130_trg_permit_merge_gate.sql:38-41`](../../verticals/mainline/db/migrations/0130_trg_permit_merge_gate.sql) |

**Measured today.** In a scratch database, a four-table toy with one named `CHECK` and one trigger,
written at by a plain database client with no application of ours anywhere in the path:

```
UPDATE subject SET state = 'merged' WHERE id = 1;
ERROR  23514  failed to satisfy CHECK constraint ((state != 'merged') OR (open_blocking = 0))

-- forge the counter to zero, so the table's own rule is now satisfied:
UPDATE subject SET state = 'merged', open_blocking = 0 WHERE id = 1;
ERROR  P0001  DEMO: merge refused by fn_demo_merge_gate — re-derived open obligation count is 1
              while the projected counter reads zero
```

Then the same illegal history with one mechanism removed at a time. Drop the trigger and the
honest write is still refused, `23514`. Put the trigger back, drop the rule, and the dishonest
write is still refused, `P0001`. Transcript steps 22 to 28.

**What this does not claim.** That toy is four tables in a scratch database and demonstrates what
the platform gives you. It is **not** the product's structural-redundancy claim. That claim is
made in exactly one place — [`packages/trappoint-conformance/unweld/harness.py`](../../packages/trappoint-conformance/unweld/harness.py)
— and its own opening lines say why no runtime test may assert it.

**Why we single it out.** Two mechanisms of different kinds, both declared, both readable back out
of the database by anyone with a SQL prompt (`SHOW CREATE TABLE` prints the constraint, name and
all). We did not have to build a permission layer, an approval service, or a queue to get a write
refused. We wrote the rule down where the data is.

---

## 2. The strongest isolation setting is what you get without asking

**Plainly.** Our gate recounts, inside the transaction that is doing the merge, the very rows
someone else might be inserting at that moment. Under a weaker setting that recount can be
correct when it is read and wrong by the time it is used. On CockroachDB the strongest setting is
already in force before anyone configures anything.

**Measured today.** First statement on a brand-new connection, no `SET` issued on it beforehand:

```
SHOW default_transaction_isolation;   -- serializable
BEGIN; SHOW transaction_isolation;    -- serializable
```

And two transactions made to collide on the same rows report it with one specific code:

```
40001  restart transaction: TransactionRetryWithProtoRefreshError: ... (RETRY_SERIALIZABLE)
```

Transcript steps 29 to 31.

**What it saved us, concretely.** Three things we did not have to build, and one we did. The first
is for readers who write SQL; the other three read plainly.

- **No hand-built locking.** None of the usual machinery for making two writers take turns: no
  `SELECT … FOR UPDATE` ordering to design and review, no advisory locks, no version column that
  each writer has to re-check before it commits.
- **No deployment step to audit.** Our client asserts the level anyway as the first statement of
  every gate transaction — `ISOLATION_STATEMENT` at
  [`packages/trappoint-core/src/trappoint_core/gate.py:56`](../../packages/trappoint-core/src/trappoint_core/gate.py)
  — but that assertion re-states the cluster's own default rather than changing it. There is no
  `ALTER ROLE … SET default_transaction_isolation` anywhere in our deploy chain, and nothing about
  a pool's session defaults that a reviewer has to go and check.
- **One code to retry, not a family.** The retry loop retries `40001` and nothing else, and says
  so in its own docstring —
  [`packages/trappoint-core/src/trappoint_core/retry.py:173`](../../packages/trappoint-core/src/trappoint_core/retry.py).
  The four refusal codes are attempted exactly once, ever. That rule is only writable because the
  platform reports a serialization conflict as one stable code.
- **What we did still build:** the assertion itself, because a level nobody states is a level
  somebody can change in a deploy without touching a line of code.

**What this does not claim.** It does not say `SERIALIZABLE` is what makes our gate correct. Our
own architecture note records the opposite and is the stricter reading:
[`docs/architecture/01-the-mechanism.md:269-274`](../architecture/01-the-mechanism.md) states that
the gate stays welded even at a weaker setting called `READ COMMITTED` — because the two writers
change the same physical row, so their collision is real data rather than something the database
has to be clever enough to infer. The praise here is narrower and still worth writing down: the
strongest level cost us nothing to obtain, and the gate's ability to notice that a stored counter
and the rows it summarises have drifted apart is at full strength on day one, rather than after an
opt-in somebody has to remember.

---

## 3. The error codes are exact enough to put on a screen as evidence

**Plainly.** When our demo refuses a merge, the screen shows the five-character code the database
returned and the name of the rule that produced it. We can do that because the codes are stable
and specific, and because one of them arrives with a machine-readable name attached rather than
buried in prose.

**Measured today**, read straight off the driver's error object:

| What was tried | SQLSTATE | Name field | Message text |
|---|---|---|---|
| merge with an honest counter | `23514` | `demo_gate_closed_when_issued` | `failed to satisfy CHECK constraint ((state != 'merged') OR (open_blocking = 0))` |
| merge with a forged counter | `P0001` | *(empty)* | `DEMO: merge refused by fn_demo_merge_gate — …` |

Two things follow, and both shaped our code.

The `23514` refusal **carries the constraint's name in its own field**, not in the message. The
message text holds the expanded expression instead. So our diagnosis function reads the field and
never parses the message —
[`verticals/mainline/apps/demo-api/src/mainline_demo_api/refusal.py:184-197`](../../verticals/mainline/apps/demo-api/src/mainline_demo_api/refusal.py),
which states its two channels in order and says there is deliberately no third.

The `P0001` refusal **carries no name**, because there is no constraint behind it. That absence is
why our own `RAISE` writes `refused by <schema>.<function>` into its message and treats the
function name as the exhibit —
[`verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:38-42`](../../verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql).

**The codes this product puts on screen, and where each is defined.**

| Code and exhibit | Defined at |
|---|---|
| `23514` · `gate_closed_when_issued` | [`0050_permit.sql:114`](../../verticals/mainline/db/migrations/0050_permit.sql) |
| `23514` · `cr_gate_closed_when_merged` | [`0051_change_request.sql:85`](../../verticals/mainline/db/migrations/0051_change_request.sql) |
| `P0001` · `mainline.fn_permit_merge_gate` | [`0115_fn_permit_merge_gate.sql:44`](../../verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql) |
| `P0001` · `mainline.fn_cr_merge_gate` | [`0116_fn_cr_merge_gate.sql:44`](../../verticals/mainline/db/migrations/0116_fn_cr_merge_gate.sql) |
| `42501` on a privilege refusal | named as a constant at [`cr_gate_run.py:222`](../../verticals/mainline/apps/demo-api/src/mainline_demo_api/cr_gate_run.py); the grant it comes from is [`verticals/mainline/db/GRANTS.yaml:761`](../../verticals/mainline/db/GRANTS.yaml), which gives `mainline_api` `SELECT` on `mainline.cr_event` and no `INSERT` |

The demo's expected codes are written into the seed file itself, before any run, at
[`verticals/mainline/db/seeds/demo/demo_permit.sql:49-62`](../../verticals/mainline/db/seeds/demo/demo_permit.sql).
The component that renders a code on screen — and says so loudly when a code falls outside the set
we modelled — is
[`verticals/mainline/apps/console/src/design/primitives/Sqlstate.tsx:36-58`](../../verticals/mainline/apps/console/src/design/primitives/Sqlstate.tsx).

**One of these five was not reproduced by this program.** `42501` needs a second database user,
and this program creates nothing outside its one scratch database. It is reproduced live by a
sibling program, [`scripts/upstream/repro_privileges.py`](../../scripts/upstream/repro_privileges.py),
whose transcript records `42501 user upstream_probe_… does not have EXECUTE privilege on procedure
merge_permit` — [`evidence/upstream/F01-has-function-privilege.json`](../../evidence/upstream/F01-has-function-privilege.json).

---

## What this document does not claim

Praise is only worth reading if it stops where the evidence stops. Four limits, stated here so
nobody has to find them elsewhere:

- **The toy in the transcript is a toy.** Four tables in a scratch database, created and dropped
  by one program. It shows the platform behaviour. The product's own claims are proved by the
  product's own suites.
- **Agent Skills is designed, not exercised.** It is a design written down in this repository.
  Nothing here claims it ran.
- **AWS Bedrock runs in this repository and not in the demo's request path.** The only two
  libraries the deployed code installs are `psycopg` and `psycopg-binary`, the database driver and
  its compiled half; there is no AWS client library in it at all. See
  [`docs/architecture/02-the-request-path.md`](../architecture/02-the-request-path.md), the
  paragraph headed *"Bedrock is not on this path"*.
- **The change request never gets to a merge that succeeds.** The demo's second use case shows the
  two refusals and then states, in its own response, that it cannot show a successful merge on
  that subject and why —
  [`verticals/mainline/apps/demo-api/src/mainline_demo_api/cr_gate_run.py:227-239`](../../verticals/mainline/apps/demo-api/src/mainline_demo_api/cr_gate_run.py).

---

## Read next

The measured complaints, written the same way and with the same evidence standard:
[`docs/upstream/COCKROACHDB-FIELD-NOTES.md`](COCKROACHDB-FIELD-NOTES.md), and the count of what we
could not reproduce in [`docs/upstream/STRIKE-LEDGER.md`](STRIKE-LEDGER.md).
