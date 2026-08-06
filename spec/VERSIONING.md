<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Versioning the TRAPPOINT specification

**Normative.** Current version: **`1.0.0-rc.1`**. History: [`CHANGELOG.md`](CHANGELOG.md).

TRAPPOINT is versioned under **Semantic Versioning 2.0.0**, with one substitution that decides
everything else: the "public API" is not a set of function signatures. It is **the set of writes a
conformant database refuses**.

> A change is **breaking** if a deployment that was conformant at version `X` can be non-conformant
> at version `Y` without changing a single line of its own code.

That is the whole rule. Everything below is its application.

---

## 1. What is versioned

| Artefact | In the public API |
|---|---|
| `TRAPPOINT-SPEC.md` — the calculus, the kernel properties, the state-machine contract | **yes** |
| `invariants/I01–I16.md` — the sixteen normative statements | **yes** |
| `errors.md` — the SQLSTATE contract and the exhibit semantics | **yes** |
| `wire/refusal.schema.json`, `wire/obligation.md` | **yes** |
| `binding/vertical.schema.json` and the Authority Source Contract | **yes** |
| `conformance/manifest.toml` — ids, expectations, profiles, depths | **yes** |
| exhibit names (constraints, unique indexes, trigger functions) referenced by the manifest | **yes** |
| rationale, worked examples, prose, `note` fields, performance guidance | no |
| the reference vertical's stub SQL, fixtures, tooling internals | no |

If it is on the "yes" list, changing it changes what a database must do, and the rules in §2 apply.

---

## 2. The bump rules

### 2.1 MAJOR

Any of these, without exception:

1. **Adding an invariant.** `I17` would be a `2.0.0`, on the day it is added, because every deployed
   vertical becomes non-conformant against a rule it could not have implemented. This is the reason
   the catalogue is small, closed, and hard to get into. **A specification that can grow cheaply is a
   specification nobody can build against.**
2. **Removing or renumbering an invariant.** Identifiers are permanent. A retired invariant keeps its
   number and gains a `RETIRED` banner; the number is never reused.
3. **Restating an invariant so an implementation that passed can fail.** Including narrowing a
   defined term, or moving a condition from SHOULD to MUST.
4. **Tightening any MUST**, adding a new MUST, or promoting a SHOULD.
5. **Renaming an exhibit** — a constraint, unique index or trigger function named in the manifest.
   Consumers parse these names, ledgers store them verbatim, and a stored exhibit whose name no
   longer exists is an evidentiary problem, not a refactor.
6. **Adding a required field** to a wire schema, removing a field, changing a field's type, or
   changing what a producer may set.
7. **Adding a required key** to `vertical.toml`, or making an optional key mandatory.
8. **Adding an enumerated value a consumer must handle** — a new `naa_reason`, a new expectation
   class, a new modelled SQLSTATE.
9. **Changing the `dedupe_key` tuple**, which changes the identity of every obligation ever
   materialised.
10. **Adding a conformance case that fails an implementation which violates no existing MUST.** If
    the case is testing something new, the something new is a new invariant, and rule 1 applies.

### 2.2 MINOR

1. A **new optional extension point**: an optional binding key, an optional wire field, a new
   capability switch, a new `[[obligation_source]]` shape, a new `naa.kind` a consumer may ignore.
2. A **new profile**.
3. A **new conformance case that only fails implementations already violating an existing MUST.**
   This is the important one and it is deliberate: the suite may get sharper at MINOR. An
   implementation that breaks because the suite finally caught it was never conformant.
4. Widening a permitted value set where every previously-legal value stays legal.
5. New `requires` tokens, new generated artefacts, new runner flags.

### 2.3 PATCH

1. Documentation, rationale, worked examples, `note` fields, formatting.
2. **Error *message* text.** No client may depend on the sentence after the `MAINLINE:` /
   `TRAPPOINT:` prefix. The prefix itself is MAJOR (§2.1 rule 5, by extension: clients parse it).
3. Performance guidance and index recommendations.
4. **Correcting a manifest `expect_constraint` to the name the platform actually reports** for a
   name the *platform* generates (`*_pkey`, `*_key`). No MUST changed; the manifest was wrong about a
   fact, not about a rule.
5. Correcting a factual error in a non-normative section.
6. Fixing a schema that was more permissive than its prose said, where no conformant implementation
   could have relied on the permissiveness.

### 2.4 The tie-breaker

When a change could be argued either way, **it is the higher bump**. The cost of an unnecessary MAJOR
is that verticals read a changelog. The cost of a missed MAJOR is a deployment that believes it is
conformant and is not — which, for a product sold on evidentiary defensibility, is the failure mode
that ends the company rather than the sprint.

---

## 3. Pre-release and the freeze

`1.0.0-rc.N` is the pre-release series. During it, and **only** during it, the rules in §2 are
advisory: `rc.2` may break `rc.1`, and the changelog says so in plain words.

Two things must be true before `1.0.0` is tagged, and both are structural rather than editorial:

1. **The identifier namespaces are final.** `I<dd>` is reserved to `spec/`; a vertical's own schema
   invariants live in the vertical's namespace (`MI<dd>` for MAINLINE). A repository-wide lint fails
   any document outside `spec/` using a bare `I<dd>` (§3.1). This renumbering **must** land before
   the freeze, because afterwards it is a MAJOR bump by the specification's own rule 2.
2. **The conformance suite has been observed red and then green**, case by case, with the red run
   recorded. A suite that has never failed asserts nothing, and freezing a specification against an
   unproven suite freezes an assumption.

### 3.1 The identifier lint, defined precisely

The rule exists because the two namespaces collided once already, and a document that says `I02`
meaning a vertical's schema invariant is a document that will be quoted back at the wrong
specification.

**Refused** — a bare match of `\bI[0-9]{2}\b` in any file outside `spec/`.

**Permitted**, and these are the only forms:

| Form | Example |
|---|---|
| **qualified** — the token is immediately preceded by `TRAPPOINT` | `TRAPPOINT I14` |
| **linked** — the token appears inside a Markdown link whose target is under `spec/invariants/` | `` `[I14](spec/invariants/I14-minimal-refusal.md)` `` |
| **the vertical's own namespace**, which does not match the pattern | `MI25` |

**Scope.** The lint runs over every tracked file **except** `spec/**` and `LICENSES/**`. It applies
to product documents, source, migrations, telemetry configuration and dashboards. It deliberately
does **not** exempt planning documents: a plan that names an invariant is a document someone will
read as normative, and the qualified form costs nine characters.

An existing document that fails the lint is corrected by qualifying or linking the reference. It is
never corrected by widening the exemption list, and the exemption list is exactly the two entries
above.

---

## 4. Deprecation

The specification has no `@deprecated`. There are two paths and no third:

- **Retirement.** An invariant, case or field is marked `RETIRED` at a MAJOR, keeps its identifier
  forever, and the changelog records *why*, not merely *that*. Retired identifiers are never reused.
- **Superseding.** A new optional extension point is added at MINOR alongside the old one, both work,
  and the old one is retired at the next MAJOR. Verticals get one MAJOR cycle of overlap.

There is no silent removal, and no "it never really worked so it does not count" — if a deployment
could have relied on it, removing it is MAJOR.

---

## 5. How a vertical declares its target

```toml
[vertical]
name         = "MAINLINE"
spec_version = "1.0.0-rc.1"
```

`trappoint render` refuses to run when the binding's MAJOR differs from the specification in the
tree. A MINOR or PATCH difference renders with a warning naming both versions, because a vertical
targeting `1.0` against a `1.2` tree is legal — it simply does not use the newer extension points.

---

## 6. What the version number is not

It is not a maturity signal, not a release-cadence artefact, and not a marketing number. It answers
exactly one question, asked by exactly one kind of reader:

> *"I passed conformance at version X. If I upgrade to version Y and change nothing, do I still
> pass?"*

MAJOR: no. MINOR: yes, unless you were already non-conformant and had not been caught. PATCH: yes.
