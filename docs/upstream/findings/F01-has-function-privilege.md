<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# F01 — asking "may this user run this procedure?" gets a wrong answer

**Label: `REPRODUCED-TODAY`** — re-measured 2026-08-17 on **CockroachDB CCL v26.2.5**
(`x86_64-pc-linux-gnu`, built 2026/07/28 18:56:00), **local single-node CCL**.
Not measured on CockroachDB Cloud, and not claimed for it.
Transcript: [`evidence/upstream/F01-has-function-privilege.json`](../../../evidence/upstream/F01-has-function-privilege.json).
Re-run it yourself: `.venv/Scripts/python.exe scripts/upstream/repro_privileges.py`.

---

## What happened

We took away a test user's permission to run a stored procedure, and the database then
refused to let that user run it — correctly. But when we asked the database, in the same
session and about the same user, whether that user was allowed to run it, the database
answered **yes**.

So we had a safety check in our own code that asked the database that question, and it
could never have caught anything.

---

## Some words this page uses

- A **procedure** (or **routine**) is a chunk of SQL stored inside the database under a
  name, which applications run by name instead of sending the SQL themselves.
- A **role** is a database user. **Granting** a permission gives a role the right to do
  something; **revoking** takes it away.
- A **signature** is a procedure's name plus the list of argument types it takes. Databases
  let two procedures share a name with different arguments, so the signature is what
  actually identifies one.
- A **SQLSTATE** is the five-character code the database attaches to an error, so programs
  can recognise a specific failure without reading English. `42501` is "you do not have
  permission to do that."
- A **scratch database** is a throwaway database created for one measurement and dropped
  immediately after. Ours are named `upstream_f01_<8 hex characters>`.
- An **access-control list** (**ACL**) is the stored row where a database keeps
  who-may-do-what for one object.
- `has_function_privilege(...)` is a built-in the database offers so that a program can ask
  a permission question without trying the action and catching the failure.

---

## The mechanism

`has_function_privilege` can be called two ways. **The two ways do not agree.**

| how you call it | what it means | what it answered |
|---|---|---|
| `has_function_privilege('<role>', '<procedure>', 'EXECUTE')` | *may **that** role run it?* | **`true`** — wrong |
| `has_function_privilege('<procedure>', 'EXECUTE')` | *may **I** run it?* | `false` for the refused user — right |

Only the first form is blind. That is the form a checking program has to use, because a
checking program is asking about somebody other than itself.

On a fresh scratch database we created one procedure with the signature our product
actually ships, revoked the permission to run it from the test user **and** from `public`
(the built-in "everybody" role), and then asked both ways.

**The role-named form answered `true` for every role we asked — for the test user, for
`root`, for `admin`, for `public` — whether we named the procedure by its signature or by
its internal id.** Eight questions, eight `true`s. Meanwhile the same test user, in the
same session, was refused by the engine:

```
42501 user upstream_probe_526fccdd does not have EXECUTE privilege on procedure merge_permit
```

(The `526fccdd` is random per run — every run makes a fresh user and a fresh database, so
your copy will show different hex.)

**A check built on that form cannot fail, and a check that cannot fail is decoration.**

### It is not failing to look things up

We ran two controls to rule out the dull explanation that the function short-circuits to
`true` without resolving its arguments. It does resolve them — both errors below are the
*correct* behaviour, and they show the lookup really happens:

```
has_function_privilege(<real role>, 'mainline.no_such_routine_at_all(INT)', 'EXECUTE')
    -> 42883  unknown function: mainline.no_such_routine_at_all()
has_function_privilege('no_such_role_…', '<real procedure>', 'EXECUTE')
    -> 42704  role 'no_such_role_…' does not exist
```

So the `true` is a decision reached after both arguments resolved, not an accident.

### What we can and cannot say about the cause

We can say this much, because we measured it: the procedure's stored access-control list
read empty (`NULL`) in **every** state — after the revoke, after a grant, and after a
second revoke — even though the engine honoured all three. So that row is not where the
answer lives.

We cannot blame the empty row, though, and this is the part that keeps the finding honest:
**the table equivalent is equally empty and still gets the right answer.** `pg_class.relacl`
for our test table also read `NULL`, and `has_table_privilege` was correct anyway. An empty
stored list is therefore not an excuse.

We did not read CockroachDB's source, so we are not naming a line of code. We are naming a
behaviour, with a program that shows it.

### The negative control, on the same database, in the same run

This is where the finding gets its force. The **table** version of the identical question
tracks reality exactly:

| question | answer | what actually happened |
|---|---|---|
| `has_table_privilege(<user>, 'mainline.permit', 'SELECT')` | `true` | `SELECT` succeeded |
| `has_table_privilege(<user>, 'mainline.permit', 'INSERT')` | **`false`** | `INSERT` refused, `42501` |

Same database, same session, same user, same shape of question. One function matches the
engine and the other does not. That is why we still trust `has_table_privilege` for tables
and stopped trusting `has_function_privilege` for procedures.

---

## Where we were wrong

**Two things, and one of them is a claim we had already published.**

1. **We said "for everybody", and that is too broad.** Our earlier internal account
   (`docs/regression/GUARD.md` § *Two things this guard found on its first run*, and
   `docs/submission/JUDGING-AXES.md`) said `has_function_privilege` answered `true` "for
   that role, for `root`, for `admin`, for `public`, for everybody." Measured properly
   today, the last two words are wrong. The **two-argument** form — where you do not name a
   role and the database answers about whoever is asking — is **correct**: `false` for the
   refused user, `true` for `root`. Calling the whole built-in a stub overstated it. The
   defect is narrower and more specific than we said, which makes it more useful.

2. **We had a counter-reading in our own tree and had to test it rather than argue with
   it.** `docs/demo/cr-gate-measurements.md` reads one of these `true` answers as
   CockroachDB's correct default for `public` on a procedure whose access-control list was
   never touched — which, if right, would make the behaviour correct and our reading the
   error. That counter-reading is reasonable, and today's run does not refute it *on its own
   terms*: a procedure nobody ever revoked anything from probably should answer `true`.
   What it cannot do is rescue the function, because the same `true` survives an explicit
   revoke that the engine then enforces. We designed today's measurement specifically so
   that a `false` would have struck this finding entirely.

---

## What better would look like

**Make the role-named form resolve EXECUTE through the same path the executor uses** — the
path `has_table_privilege` already uses successfully on the same build — so that it is able
to return `false`. A permission-inspection built-in that cannot return `false` is worse than
one that does not exist, because programs are written against it.

If that is not near-term work, the cheap interim is a documentation change we would have
happily taken instead: **one line on the `has_function_privilege` page saying the role-named
form does not currently reflect routine `EXECUTE` grants.** That line would have saved us
the afternoon, and it is a pull request rather than a project.

---

## How we found it, and what it cost

We did not find this because something broke in production. We found it because we planted a
deliberate violation — revoke the permission, then check that our own guard goes red — and
the guard stayed green. The plant was built to make the check fail, and the check would not
fail.

The cost was an afternoon, plus rewriting the check to read `SHOW GRANTS` and expand role
membership by hand — which costs us the two things the built-in would have done for free:
stripping the argument list off the procedure's name (that is [F02](F02-show-grants-signature.md))
and following one role's membership in another. The replacement *can* go red, which is the
whole point.

The general lesson is not about CockroachDB. **A check nobody has ever seen fail is not
evidence of health.**

---

## Reproduce it

```
.venv/Scripts/python.exe scripts/upstream/repro_privileges.py
```

The script creates `upstream_f01_<8 hex>` and a throwaway role, does everything inside them,
and drops both in a `finally` block — it prints the name it created and the name it dropped,
and counts what it left behind (`0`). It refuses to run against any host other than
localhost. It makes no AWS call, touches no CockroachDB Cloud cluster, and prints no
credential. It exits `0` while this finding still reproduces and `1` the day it stops.
