<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Changelog — TRAPPOINT specification

All notable changes to the specification are recorded here. The format follows
*Keep a Changelog*; the versioning rules are normative in [`VERSIONING.md`](VERSIONING.md).

During the `1.0.0-rc.*` pre-release series the bump rules are **advisory**: a later `rc` may break an
earlier one, and every such break is listed under **Breaking** with a reason.

---

## [Unreleased]

Nothing yet.

---

## [1.0.0-rc.1] — amended 2026-08-07, before tagging

`rc.1` was never tagged and has no downstream consumer, so these four corrections are folded into it
rather than issued as `rc.2`. They are listed separately because two of them contradict what the
document said three days ago, and a specification that edits itself silently is not one.

### Fixed — `key_columns`, a defect that would have broken the first binding

`[[authority_source]]` could name the lookup columns of the **projected row** (`key`) but not the
columns of the **authority relation** they are matched against. Where the two sides use different
names — and they do in the only binding that matters, `blocking_check.commit_id` against
`clause_blame_current.as_of_commit` — a renderer had no way to emit a correct `WHERE` clause and
would have produced SQL naming a column that does not exist. Added the optional `key_columns` array,
defaulting to `key`; added render refusal **A-9** on a length mismatch; corrected the worked SQL in
`binding/authority-source.md` §4, which was wrong in exactly this way.

### Changed — the identifier lint is now defined by its command

`VERSIONING.md` §3.1 previously permitted two escape hatches, a *qualified* form (`TRAPPOINT I14`)
and a *linked* form (`[I14](spec/invariants/I14-…)`). **Neither is implementable.** The lint is a
bare `\bI[0-9]{2}\b` grep and both forms contain a bare match — the linked form twice, once in the
link text and once in the path. A lint whose documented exemptions its own implementation cannot
honour invites the grep to be weakened until it agrees with the prose, which is how a namespace rule
dies. The command is now the definition, there are no exemptions, and §3.2 adds the citation
convention that makes the rule liveable: outside `spec/`, an invariant is cited by **slug**
(`TRAPPOINT/projected-refusal`), with the full identifier-to-slug mapping in one table.

### Added — four complete refusal payloads and sixteen negative assertions

`wire/refusal.md` §8 carries four payloads — counter refusal, lattice refusal with no legal verdict,
authority gap, budget-exhausted composite — that validate against the shipped schema with no elision,
plus §8.5, a table of sixteen mutations the schema **rejects**. The §1 illustration is now marked as
elided, because it never validated and looked as though it should. An emitter now has something to
diff against instead of a description to interpret.

### Fixed — a TOML placement trap in the binding, documented where it bites

A bare top-level key written *after* any `[table]` header belongs to that table, so
`emit_outbox = true` placed below `[capabilities]` parses as `capabilities.emit_outbox` and the
binding fails validation with a message about the wrong key. This was found by validating a
MAINLINE-shaped binding against the schema rather than by reading it. The rule is now stated in the
`emit_outbox` description, which is where a binding author is looking when it happens.

### Known limitation carried forward

The identifier lint runs over `*.md` only, so a migration's `-- I02` header comment is unaffected and
the migrate linter's requirement that every migration cite one is undisturbed. Nine citations across
five files outside `spec/` currently fail the lint — four domain plans under `docs/leads/` and the
repository README. They are owned outside `spec/` and are corrected by rewriting each citation as a
slug, never by widening the grep.

---

## [1.0.0-rc.1] — 2026-08-04

First published specification. Everything below is new; the list exists so that `rc.2` has something
to be a diff against.

### Added — normative documents

- `TRAPPOINT-SPEC.md`: the PROJECT · PIN · REFUSE calculus (rules `P-1`–`P-5`, `N-1`–`N-4`,
  `R-1`–`R-4`), the four kernel properties with their proof artefacts, the gated-subject state
  machine contract, the conformance definition `C-1`–`C-6`, and the SemVer rule.
- `invariants/I01–I16`: sixteen normative files, each with the fixed skeleton **NORMATIVE
  STATEMENT** · **MECHANISM** · **OBSERVABLE** · **CONFORMANCE** · **NOT CLAIMED**.
- `errors.md`: the SQLSTATE contract.
- `wire/refusal.md` + `wire/refusal.schema.json` (JSON Schema draft 2020-12): the refusal payload,
  its minimal unsatisfiable subset and its nearest admissible alternative.
- `wire/obligation.md`: the obligation record, and the wire-level statement of which fields a
  producer may set.
- `binding/vertical.schema.json` + `binding/authority-source.md`: the vertical binding schema and the
  Authority Source Contract.
- `conformance/manifest.toml` + `conformance/README.md`: 71 cases, 45 of them on the reference
  profile.

### Added — rules that resolve a contradiction in the source architecture

Each of these is a ruling, not a restatement. They are listed separately because an implementer
reading the architecture documents will find text that predates them.

- **`R-3` Exhibit Uniqueness.** A refusal-bearing constraint, index or trigger-function name MUST be
  unique across the whole schema, not merely within its table. The exhibit name alone must identify
  the refusal. Consequences: `linear` / `cr_linear`, `ctr_nonneg` / `cr_ctr_nonneg`,
  `substantive` / `carried_substantive`, `bounded` / `carried_bounded` / `predicate_bounded`,
  `fk_version` split into `fk_check_version` / `fk_permit_clause_version` / `fk_cr_clause_version`.
- **The S-RULE (synthetic-code ban), `errors.md` §3.3.** Substrate procedural code MUST NOT `RAISE`
  with `23514`, `23503`, `23505` or `40001`. `diag.constraint_name` is empty on a synthetic raise, so
  such a raise produces an exhibit with no name; and a synthetic `40001` would be retried forever by
  a conformant client. All procedural refusals use `P0001`.
- **The re-derivation corollary.** Where a condition is also expressible as a `CHECK`, procedural code
  MUST NOT pre-empt it: the trigger re-derives from base tables and raises `P0001` only on drift or on
  a condition no `CHECK` can hold. The merge-gate trigger therefore does **not** raise for a non-zero
  obligation counter — the counter's own `CHECK` refuses, by name. This preserves
  `gate_closed_when_issued` as the observable exhibit.
- **The strictest-projection corollary.** A projection trigger whose typed-verdict lookup misses MUST
  project the strictest legal values and let the composite foreign key fire with its name attached,
  rather than raising a synthetic `23503` or leaving a `NOT NULL` projection unset (which would
  produce `23502`, outside the taxonomy). Expressed in the binding as
  `raise_via = "strictest_projection"`.
- **The four expectation classes, `errors.md` §1.** `42501` was previously both required by the role
  matrix and forbidden by the "taxonomy is total" rule. Resolved by defining the taxonomy as total
  **over the gate path**: `42501` is a *pre-gate* DENY, not a gate refusal, and lives in its own
  class. `00000` (ADMIT) is added so that cases proving a legal path stays legal carry a uniform,
  machine-checkable expectation.

### Added — manifest conventions

- `expect_constraint` is defined for every code, including `P0001` (the fully-qualified raising
  object), `40001` (the projected column carrying the materialised conflict) and `42501`
  (`grant:<verb>:<object>:<role>`), so that **no case may assert a SQLSTATE alone**.
- `requires` tokens: a case whose relation, role or policy is absent **skips with a printed reason**
  and is never counted as passed.
- `asserts_stored_row`: positive assertions about what the database *stored*, so the projection
  cases (`CF-07`, `CF-11`, `CF-19`, `CF-44`, `CF-46`) cannot pass against an implementation that
  trusted the client and refused for an unrelated reason.
- `refusal_depth_min`, with `>= 2` on every merge-gate case and `3` on `CF-10`.

### Fixed

- The reference to structural redundancy now appears in exactly one place with its proof artefact
  (the unwelding harness), and every other mention states that at runtime the deterministic raise
  fires first. No document, case or generated artefact may assert redundancy from runtime behaviour.

### Known gaps, stated rather than deferred silently

- **Platform-generated exhibit names are unverified.** `merge_record_pkey`, `permit_event_pkey`,
  `ledger_leaf_pkey` and `blocking_check_dedupe_key_key` follow the conventional
  `<table>_<columns>_key` / `<table>_pkey` form. The runner compares against the name the database
  reports; correcting the manifest to match is a PATCH.
- **Twenty-six cases are `mainline`-only. Twenty-five of them carry `requires`** — each naming the
  relation, role or policy it needs and the milestone at which it can first be green — and skip with a
  printed reason rather than being silently absent. The twenty-sixth, `CF-24` (the rationale-length
  floor), carries no `requires` and never will: it is vertical policy, not a kernel property held back
  by a missing table, and a `requires` token would falsely imply the reference vertical could earn it.
- **`I16` (external witness) has one conformance case and it cannot be green until a genuinely
  adverse witness exists.** Split-view resistance MUST NOT be claimed before then, and the invariant
  file says so in its NOT CLAIMED section.
- **`I08` (certified null) and `I15` (allegation firewall) have two cases each, and every one of them
  is `mainline`-only** — `CF-62`/`CF-65` and `CF-68`/`CF-69` respectively. Neither invariant has a
  single case runnable on the reference profile, so a `45/45` reference run asserts **nothing** about
  either. Both are under-covered relative to their importance and are the first candidates for new
  cases at `rc.2` — which, per the versioning rules, is a MINOR bump only if the new cases fail
  nothing that was already conformant.

### Not in this version

Anchoring (RFC 3161, beacon, witness quorum) is specified under `spec/custody/` rather than here.
The checkpoint wire format is `spec/wire/checkpoint.md` and is versioned separately.

---

[Unreleased]: https://github.com/Shaugato/mainline/compare/spec-v1.0.0-rc.1...HEAD
[1.0.0-rc.1]: https://github.com/Shaugato/mainline/releases/tag/spec-v1.0.0-rc.1
