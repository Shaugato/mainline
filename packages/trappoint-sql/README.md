<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `trappoint-sql` — the render engine and the Authority Source Contract

Two things live here, and the second is why the distribution exists.

**A deterministic SQL renderer.** Kernel templates plus one vertical binding produce
committed, reviewable SQL. `trappoint render --check` is a zero-diff assertion in CI, so
the SQL a database applies is provably the SQL the templates and the binding describe —
not something a hand edit drifted into.

**A compile-time refusal.** A template marks a projected gate column with a
`{# @projects blocking_check.severity #}` pragma. If `vertical.toml` carries no
`[[authority_source]]` entry backing that column, `trappoint render` exits non-zero and
names the column. Specification rule `P-2` — *a projection is derived from a declared
authority, never from the inserter* — stops being a discipline someone remembers during
code review and becomes a build error.

---

## Why the contract is the point

The most common way a gate quietly stops working is not a deleted constraint. It is a
column that *looks* projected and is in fact supplied:

```sql
-- the gate reads this column
CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0)

-- ... and the obligation feeding it declares its own severity
INSERT INTO blocking_check (..., severity, virulence) VALUES (..., 1, 'routine');
```

Every constraint still exists. Every test still passes. The gate is now enforcing a claim
the writer made about itself. Nothing is missing except **authority**, and absence of
authority is invisible to every other check in the repository. Adversarial finding `S1`
is exactly this failure one hop upstream of the flagship claim.

The contract makes that absence a thing the build can see. Rules `A-1` … `A-9` are
specified in [`spec/binding/authority-source.md`](../../spec/binding/authority-source.md)
§3 and implemented in [`src/trappoint_sql/binding.py`](src/trappoint_sql/binding.py).

### One scoping decision, stated out loud

`A-5` ("an entry projects a column no template declares") is enforced **per relation**.
An entry projecting `blocking_check.severity` when *no template in the tree renders any
projection onto* `blocking_check` is reported as **pending**, not refused — the gate
templates land in migration band `0100+`, several workers after this one, and a renderer
that refused a correct declaration for a table that does not exist yet would force every
binding to be written backwards. The moment *any* template projects onto
`blocking_check`, `A-5` becomes a hard refusal for every column of that relation.

The scope is derived from the **template set**, never from the binding, so it cannot be
configured away. `trappoint render` prints every pending column on every run, so "the
contract passed" is never read as "every projection in the design is backed".

---

## Usage

```bash
trappoint render                       # render every binding in the tree
trappoint render --check               # zero-diff assertion; writes nothing
trappoint render --binding verticals/mainline/vertical.toml
trappoint render --list                # which bindings would be rendered
trappoint render --check --verbose     # ... and which file came from which template
```

Exit codes match `trappoint migrate`: `0` did what it said · `1` **refused** (unbacked
column, unmeasured capability, banned token, or a `--check` diff) · `2` bad invocation.

---

## Determinism, and why it is a requirement

`--check` is only meaningful if a render is byte-reproducible, and the Authority Source
Contract is only binding while the committed SQL is what the declaration produced. So:

| Setting | Why |
|---|---|
| `StrictUndefined` | a typo in a template variable is a refusal, never an empty string rendered silently into a `GRANT` |
| `trim_blocks`, `lstrip_blocks` | block tags leak no whitespace, so a reformatted template is a reviewable diff |
| `keep_trailing_newline` | files end in exactly one newline, on every platform |
| sorted template load order; explicitly ordered context sequences | no dictionary iteration order reaches the output |
| `newline="\n"` on write, **bytes** on compare | on Windows the default text mode would translate `\n` to `\r\n` and `--check` would fail on every file for a reason unrelated to the SQL |

**One template renders many files.** One DDL statement per file is not negotiable —
CockroachDB DDL is not transactional across statements, so a multi-statement file is not
atomic and `dirty` becomes undiagnosable. A template emits a stream split on a
`-- @file <name>` sentinel line. The sentinel is a SQL comment on purpose: a stream that
somehow reached a database unsplit would still parse.

---

## Capability switches (ruling `D5`)

A capability under a dated `GT-*` check is a **render-time switch, never a runtime
branch**. Both branches emit committed, readable SQL, so the fallback is something a
reviewer reads rather than a branch a reviewer trusts.

`trappoint render` refuses to run without a `g1-attestation.json` — declared by path in
`[capabilities].attestation` — that answers every capability a template declares with
`{# @capability <name> #}`. Three states:

| Status | Meaning |
|---|---|
| `PASS` | measured, works, primary branch renders |
| `FALLBACK-SELECTED` | measured, does not work, fallback renders; any dated claim depending on it is withdrawn in the same commit |
| `UNKNOWN` | not measured. **Refused.** `PL-3` forbids a dated path on an unproven capability, and a default is how an unproven capability reaches production |

The binding does not overrule the measurement: a binding selecting `stored_digest =
"stored"` against an attestation recording `FALLBACK-SELECTED` is a refusal.

The attestation shipped here was measured on 2026-08-08 against
`cockroachdb/cockroach:v26.2.5` running locally, pinned to the Cloud version.
**`GT-13` (`digest()` in a `STORED` column) PASS** and **`GT-05` (`pg_get_triggerdef`)
PASS**; both statements and both results are quoted in the file.

---

## The role model, and a request to the spec owner

ARCHITECTURE.md §11.2 names nine roles. `vertical.schema.json` 1.0 exposes six under
`[roles]` and closes the table with `additionalProperties: false`, so `recaller`,
`auditor` and `qa` cannot be named by a binding at all.

Rather than invent a config key the specification does not have, the renderer **derives**
every slot and lets `[roles]` override the six the spec can express. The derivation is
the rule §11.2 already follows:

* **agent and service roles are cluster-global constants** — `agent_gate`,
  `agent_projector`, `agent_recaller`, `svc_disposition`, `auditor_ro`,
  `quality_assurance`;
* **the three roles that own or administer a schema are schema-scoped** —
  `<schema>_migrator`, `<schema>_owner`, `<schema>_auditor`.

For `schema = "mainline"` that reproduces §11.2's nine names exactly, with no table of
hard-coded vertical knowledge anywhere in the substrate.

> **Requested of the spec worker, next MINOR:** add `recaller`, `auditor` and `qa` keys
> to `$defs.vertical.roles`. Adding optional keys is MINOR under `spec/VERSIONING.md`,
> and it would let a binding name all nine rather than six. Until then the derivation
> above is documented behaviour, not a workaround, and it is covered by a test.

### Rule `R-1`, enforced over rendered SQL

> The role that detects a precursor may never be granted a write privilege on one.

`agent_recaller` proposes candidates over HTTP; the kernel writes the obligation row
inside the serializable transaction that issues the exposure receipt. A `GRANT INSERT`
quietly reuniting those two would leave every constraint in place and every test green
while the flagship claim became false. The renderer scans every rendered statement and
refuses to emit one. Finding `S1`, at compile time.

---

## The reference vertical

[`refvertical/`](refvertical/) is a **first-class binding, not a fixture**.

1. **`K1` stops depending on `K3`.** The gate reads an authority source; in MAINLINE that
   is `mainline.clause_blame_current`, the ancestry lead's migration `0038/0039`. If the
   conformance suite needed that table, `K1` could not be green before `K3`, which
   inverts the milestone lattice. `refvertical/sql/` supplies an isomorphic closure, so
   `trappoint-conform --profile trappoint-ref` runs with zero ancestry code in existence.
2. **The extension mechanism is exercised the day it is written.** Two bindings that both
   render is the entire substrate claim; one binding is a template engine with an
   audience of one.
3. **Adding a vertical is a binding change, not a code change** — and
   `refvertical/vertical.toml` is the proof, naming different schemas, different roles
   and a different authority relation while rendering the identical templates.

Three files under `refvertical/sql/` are **hand-written stubs, not rendered**: they carry
no rendered-by banner, and `--check` leaves them alone. They are what the reference
binding's `[[authority_source]]` entries point at, isomorphic to ARCHITECTURE.md §5.3–5.4:

| File | Why it exists |
|---|---|
| `0029_clause_version.sql` | the composite FK target `(clause_uuid, commit_id)` the closure needs |
| `0038_clause_blame_closure.sql` | the append-only, generation-versioned closure |
| `0039_clause_blame_current.sql` | the `DISTINCT ON … ORDER BY closure_gen DESC` **view**, which is the relation the binding actually names |

The view is not a convenience. `clause_blame_closure` is append-only, so a recomputation
writes a *new* generation and overwrites nothing; every reader therefore owes the
discipline `max(closure_gen)`, and a reader that forgets it projects a **superseded**
severity onto a live blocking check. An older generation is the one computed with *less*
ancestry, so forgetting the discipline understates ancestral severity — the one error
direction with physical consequences. One view is how that discipline stops being
per-call-site.

> A binding may name an authority relation that no file creates, and the Authority Source
> Contract cannot see it: the contract validates a *declaration*, not a schema. That gap
> was live in this tree until `0039` landed — the reference binding named
> `trappoint_ref.clause_blame_current` while nothing created it, so the contract passed on
> a relation no projection trigger could ever read. `tests/test_bindings.py` now checks
> every declared authority relation against the `CREATE TABLE`/`CREATE VIEW` statements in
> the same vertical's SQL, which is the only place that check can live.

---

## What the contract deliberately does not check

Stated so nobody reads more assurance into a green render than it carries.

* **It does not verify the authority relation is correct.** Point a vertical at the wrong
  table and the renderer will happily project from it. What is guaranteed is that the
  projection has a *named, reviewable source* and that a missing row refuses.
* **It does not verify grants.** A template engine cannot see `GRANT` at the cluster. The
  rule that the authority relation must not be writable by the projecting role is
  asserted by a conformance case expecting `42501`, not by the renderer. `R-1` above is
  the *structural* half only: it reads rendered SQL, not cluster state.
* **It does not make the projection correct under concurrency.** That is the
  materialised-conflict property, proved by the concurrency cases.
* **It does not survive someone editing the rendered SQL by hand** — which is precisely
  why `--check` is a zero-diff assertion in CI.

---

## Layout

```
templates/            kernel SQL templates (Apache-2.0), one per migration band
src/trappoint_sql/
  binding.py          THE AUTHORITY SOURCE CONTRACT: A-1 … A-9
  attestation.py      ruling D5: capability switches from a dated measurement
  jsonschema.py       a small, dependency-free JSON Schema 2020-12 subset
  model.py            binding shape, the role model, the five schema zones
  pragma.py           @projects / @capability template pragmas
  render.py           the Jinja environment, unit splitting, guards, --check
  cli.py              `trappoint render`
refvertical/
  vertical.toml       the reference binding
  sql/                rendered migrations + three hand-written stubs
g1-attestation.json   the ground truth every render is decided by
```
