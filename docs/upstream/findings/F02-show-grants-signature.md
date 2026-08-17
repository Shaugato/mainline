<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# F02 — the database spells one procedure two ways, and we compared them naively

**Label: `REPRODUCED-TODAY`** — re-measured 2026-08-17 on **CockroachDB CCL v26.2.5**
(`x86_64-pc-linux-gnu`, built 2026/07/28 18:56:00), **local single-node CCL**.
Not measured on CockroachDB Cloud, and not claimed for it.
Transcript: [`evidence/upstream/F02-show-grants-signature.json`](../../../evidence/upstream/F02-show-grants-signature.json).
Re-run it yourself: `.venv/Scripts/python.exe scripts/upstream/repro_privileges.py`.

**This one is our bug.** It is here because admitting it is what makes
[F01](F01-has-function-privilege.md) worth reading.

---

## What happened

We asked the database two questions — "which things is this user allowed to run?" and "which
things exist?" — and it answered both correctly, but wrote the same procedure's name
differently in the two answers. Our program compared the two names as plain text, saw no
match, and reported a missing permission that was not missing.

---

## Some words this page uses

- A **procedure** (or **routine**) is a chunk of SQL stored inside the database under a
  name, which applications run by name instead of sending the SQL themselves.
- A **catalogue** is the set of tables a database keeps *about itself* — what exists, who
  owns it, who may use it. You query it with ordinary SQL.
- A **signature** is a procedure's name plus the list of argument types it takes. Databases
  allow two procedures to share a name with different arguments, so the signature is what
  actually identifies one.
- **Granting** a permission gives a user the right to do something.
- A **scratch database** is a throwaway database created for one measurement and dropped
  immediately after.
- A **SQLSTATE** is the five-character code a database attaches to an error so programs can
  recognise a specific failure. `42501` is "you do not have permission to do that."

---

## The mechanism

Two catalogue surfaces describe the same procedure. They do not spell it the same way.

```
SHOW GRANTS
    object_name -> merge_permit(uuid, bytea, text, text, jsonb, bytea, int2, bytea)

SELECT routine_name FROM information_schema.routines
    routine_name -> merge_permit
```

One carries the signature. The other carries the bare name. Neither carries the other's
spelling: we listed all 82 columns `information_schema.routines` offers and **none of them
holds the argument list**.

### The false alarm, reproduced verbatim

In the same run, before comparing anything, we granted the test user permission to run the
procedure and then watched it actually run — so we know for certain the permission was
there. Then we ran our original comparison:

```
looked for : 'merge_permit'                                                  (information_schema)
looked in  : ['merge_permit(uuid, bytea, text, text, jsonb, bytea, int2, bytea)']  (SHOW GRANTS)
matched    : False        <- WRONG. The user had just successfully run it.
```

Strip the argument list off and it is fine:

```
looked in  : ['merge_permit']
matched    : True
```

A permission checker written this way reports a shortfall that does not exist — a false
alarm on every procedure, every run. The mirror image is worse and is the reason we treat
this as more than a typo: **the same mismatch, in a check phrased as "did everything match?",
passes silently forever**, because nothing ever matches and nothing ever objects.

### A third spelling, which is the trap inside the trap

The types are also renamed on the way through. We declared the procedure with CockroachDB's
own type names and the catalogue echoed back the PostgreSQL ones:

| we wrote | `SHOW GRANTS` says |
|---|---|
| `STRING` | `text` |
| `BYTES` | `bytea` |
| `UUID`, `JSONB`, `INT2` | unchanged |

So building the expected signature string from your own `CREATE PROCEDURE` statement does
not match either. (`has_function_privilege` accepted our declared spelling happily — it
resolves the aliases. The string comparison does not.)

### There is a third spelling, and it is nearly the key

`information_schema.routines` also has a `specific_name` column, and on this build it reads:

```
merge_permit_219676
```

— the bare name with the procedure's internal id (**OID**, the number the database uses to
identify an object) glued on with an underscore. The number differs on every run, since each
run creates the procedure fresh; the *shape* is what matters. So the identifier we needed
*is* present on
the catalogue side. It is only reachable by parsing a suffix off a string, which is the same
string surgery in a different place, and `SHOW GRANTS` still exposes no id to join it
against. We are not going to call that a documented join key.

The bridge that does work is `pg_get_function_identity_arguments()`, which renders exactly
the text inside the parentheses:

```
uuid, bytea, text, text, jsonb, bytea, int2, bytea
```

So a correct normaliser can be hand-built through `pg_proc`. Nothing in either surface points
at it, and you only go looking once you already know you have the bug.

---

## Where we were wrong

**Almost all of it.** Comparing two catalogue strings as plain text without normalising them
is our mistake, made by us, and it cost the orchestrator a wrong conclusion in a single
afternoon. No database promised those two strings would be equal.

The platform half of the finding is deliberately narrow, and we would not publish it wider:
**two catalogue surfaces spell the same object two ways and ship no documented key to join
them on.** That is a rough edge, not a defect. The bug was ours.

What we changed: the checker now resolves procedures through `pg_proc` to an internal id, and
we added a standing check — `privileges.routine_signature_normalised` — whose entire job is
to go red if this trap ever stops being present in the output. A normalisation nobody
exercises is a normalisation nobody can trust.

---

## What better would look like

**Add the object's internal id (OID) as a column on `SHOW GRANTS` output.** It already
returns seven columns (`database_name`, `schema_name`, `object_name`, `object_type`,
`grantee`, `privilege_type`, `is_grantable`); an eighth stable identifier would let anyone
join grant output to `pg_proc` — or to the id already embedded in
`information_schema.routines.specific_name` — on a key instead of by string surgery, and
would make the whole class of spelling mismatch impossible rather than merely avoidable.

Cheaper and still worth having: a sentence on the `SHOW GRANTS` documentation page noting
that routines appear with their full signature while `information_schema.routines` does not,
with `pg_get_function_identity_arguments()` named as the bridge.

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
