<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The TRAPPOINT conformance suite

**Normative for the manifest format.** TRAPPOINT `1.0.0-rc.1`.
The suite itself is [`manifest.toml`](manifest.toml); this file says how to read it, how to run it,
and what a passing run does and does not entitle anyone to claim.

A fork copies four hundred lines of SQL in an afternoon. *"Passes TRAPPOINT conformance 1.0, 45/45,
refusal-depth min 2"* is a claim only the suite confers, and it is the substrate's only real moat.

---

## 1. What a case is

Every `[[case]]` is a **history** — a short sequence of writes — plus an exact expectation about how
the database responds to the last one. Seventy-one of them, each carrying an exact SQLSTATE **and** an
exact exhibit name.

Two properties make the suite worth anything, and both are easy to lose:

- **Exactness.** A case asserting *"an exception was raised"* is worthless. In a product whose
  deliverable is the diagnosis, an assertion that does not name the refusal has not tested the
  product.
- **Redness.** A case that has never failed for the right reason has not been observed to assert
  anything. Every case is written against a database that cannot yet satisfy it, observed red, and
  only then made green by the migration that owns it.

---

## 2. Field reference

| Key | Required | Meaning |
|---|---|---|
| `id` | yes | `CF-NN`. Stable forever; a retired case keeps its id and gains `retired = true` |
| `title` | yes | one line, imperative, describing the illegal history |
| `class` | yes | `gate` · `retry` · `deny` · `admit` — see §3 |
| `invariants` | yes | the `I01–I16` this case proves; may be empty only for platform-law cases |
| `mi` | yes | the vertical's own schema invariants proved; may be `[]` |
| `anomaly` | yes | `A1`–`A14`, or `none` for a static illegal history |
| `expect_sqlstate` | yes | exactly one code; never empty |
| `expect_constraint` | yes | the **exhibit name**; never empty (§4) |
| `profiles` | yes | which bindings run it |
| `refusal_depth_min` | yes | minimum surviving mechanisms under unwelding (§6) |
| `milestone` | yes | the milestone at which the case can first be green |
| `requires` | no | capability tokens; a case whose requirement is absent **skips with a reason** |
| `secondary_sqlstate` / `secondary_constraint` | no | a second assertion in the same history |
| `payload_schema` / `asserts_payload` | no | the case additionally validates a refusal payload |
| `asserts_stored_row` | no | a positive assertion about what the database *stored*, not only what it refused |
| `note` | no | rationale; never load-bearing for the runner |
| `retired` | no | present and `true` only on a case the spec has retired; MAJOR bump |

### 2.1 `asserts_stored_row` is not decoration

Five cases carry it — `CF-07`, `CF-11`, `CF-19`, `CF-44`, `CF-46` — and they are the strongest cases
in the suite. `CF-07` asserts that a check
inserted claiming `(1, 'routine')` is **stored** as `(5, 'blood_fatal')`; `CF-19` asserts a
client-supplied rank of 6 is **stored** as 2. Without those assertions both cases would pass against
an implementation that trusted the client and merely happened to refuse for an unrelated reason.
**The rewrite is the claim. The refusal is the consequence.**

---

## 3. The four classes

| Class | Legal codes | Meaning |
|---|---|---|
| `gate` | `23514` `23503` `23505` `P0001` | the gate decided: no |
| `retry` | `40001` | the transaction is undecided; the client retries |
| `deny` | `42501` | the writer never reached the gate — refused by grant or policy |
| `admit` | `00000` | the history must **complete**; the case proves a legal path stays legal |

`test_taxonomy_totality` applies to `gate` and `retry` cases: any SQLSTATE outside
`{40001, 23514, 23503, 23505, P0001}` fails the suite, because it means the database refused for a
reason nobody modelled. `deny` cases assert `42501` explicitly, and `admit` cases assert success.

The three `admit` cases exist because a gate that refuses everything is not a gate. `CF-11` proves
deduplication *absorbs* rather than refuses; `CF-22` proves the gate transaction still succeeds under
forced row-level security; `CF-46` proves the history is reconstructible from the event chain.

---

## 4. `expect_constraint` — the exhibit

Never empty. Its meaning depends on the code (normative in [`../errors.md`](../errors.md) §3.1):

| Code | The exhibit is |
|---|---|
| `23514` `23503` `23505` | the constraint or unique-index name from `diag.constraint_name`, verbatim |
| `P0001` | the fully-qualified raising function, e.g. `mainline.fn_permit_merge_gate` |
| `40001` | the projected column that carried the materialised conflict, `schema.table.column` |
| `42501` | `grant:<verb>:<object>:<role>`, or the RLS policy name |
| `00000` | the SQL object that had to permit the write |

### 4.1 Names the platform generates

Four exhibits are names the database assigns rather than names the DDL declares:
`merge_record_pkey`, `permit_event_pkey`, `ledger_leaf_pkey`, `blocking_check_dedupe_key_key`. The
manifest records the conventional `<table>_<columns>_key` / `<table>_pkey` form. A runner MUST
compare against the name the database actually reports; where the platform's convention differs, the
**manifest is corrected** and that correction is a **PATCH** bump, because no MUST changed.

Everywhere else, the exhibit is a name the DDL declares explicitly, and specification rule **R-3**
requires it to be unique across the whole schema — which is why the mirrored change-request objects
carry distinguishing names (`linear` / `cr_linear`, `bounded` / `carried_bounded`,
`fk_check_version` / `fk_permit_clause_version` / `fk_cr_clause_version`).

---

## 5. Profiles

| Profile | Binding | Cases |
|---|---|---|
| `trappoint-ref` | the reference vertical shipped with the substrate | **45** |
| `mainline` | the MAINLINE vertical | 71 |

Exactly forty-five cases carry `trappoint-ref`. That number is not a coincidence and not a target: it
is every case expressible against the kernel tables alone, without any vertical's ancestry, recall,
fleet or custody schema. `trappoint-conform --profile trappoint-ref` therefore reports `45/45`, and
that string is the K1 exit criterion.

The remaining twenty-six are `mainline`-only, and they divide two ways. **Twenty-five** need a
relation, role or policy the reference vertical does not supply; each carries `requires`, and a runner
that cannot satisfy a requirement **skips with a reason** — printed, counted and reported. A skipped
case is never a passed case, and a suite that skips silently is a suite that passes by absence.

**One — `CF-24`, the rationale-length floor — carries no `requires` and never will.** It is not a
kernel property held back by a missing table; it is *vertical policy*, a number the customer signs.
A `requires` token would imply the reference vertical could earn the case by supplying a relation, and
it cannot. The distinction is recorded here rather than smoothed over, because "26 cases need more
schema" and "25 cases need more schema and 1 is not ours to hold" are different sentences and only
the second is true.

**A vertical raises its own coverage by supplying the relation, not by editing the manifest.** That
is the entire extension mechanism: two bindings that both render is the substrate claim; one binding
is a template engine with an audience of one.

---

## 6. Refusal depth and the unwelding harness

`refusal_depth_min` is the number of mechanisms that must **independently** refuse the history. It is
measured by the unwelding harness: disable one trigger, or drop one constraint, **one at a time**, on
a disposable single-node container; re-run the history; assert it still fails, by a mechanism other
than the one removed.

- Every merge-gate case carries `refusal_depth_min >= 2`. CI fails if any of them measures less.
- `CF-10` carries 3 and is the strongest structural claim in the suite: remove the deliberate raise
  and the write still fails twice over — the counter's `CHECK` on a completed row, and the mutated
  pinned epoch.
- The pre-committed response to a measured depth of 1 on a merge-gate history is **cut the mechanism,
  do not ship it.** A single-welded gate is a claim that cannot be made under oath.

> **This is the only place the structural-redundancy claim may be made.** At runtime the deterministic
> raise fires first, by construction. No case, log, dashboard, README or slide may assert redundancy
> from runtime behaviour — the proof is the matrix, and the matrix is generated in CI.

---

## 7. Generated artefacts

| Artefact | Generated from | CI fails when |
|---|---|---|
| `ANOMALY_COVERAGE.md` | the `anomaly` field | any of `A1`–`A14` has zero cases |
| `REFUSAL_DEPTH.md` | the unwelding harness | any merge-gate history measures depth `< 2` |
| `test_manifest_totality` | this manifest vs the case modules | a manifest entry has no implementation, or an implementation has no entry |
| `test_taxonomy_totality` | observed SQLSTATEs | a `gate`/`retry` case observes a code outside the taxonomy |

`test_manifest_totality` is the one that matters most, and it is bidirectional on purpose: a case
that exists in neither place cannot silently vanish, which is exactly how conformance suites rot.

---

## 8. Running it

```bash
just up                                                     # local single-node container, no cloud account
uv run trappoint-conform --dsn "$LOCAL_DSN" --profile trappoint-ref
# → 45/45 · spec 1.0 · refusal-depth min 2

uv run trappoint-conform --dsn "$LOCAL_DSN" --profile mainline
```

Cases are isolated by a fresh tenancy scope per case so the suite parallelises against one cluster.
The unwelding harness mutates schema and therefore runs **serially, on a disposable container**,
never against a cluster anything else is using.

---

## 9. What a green run entitles you to claim

**It does entitle you to say:** the database refused every history this specification says it must
refuse, by the exact mechanism it names, at the named profile and version; and that no refusal in the
run fell outside the modelled taxonomy.

**It does not entitle you to say:** that the vertical's obligations are the right obligations; that
severity was scored correctly; that a disposition is honest or that a signature was considered; that
retrieval was exhaustive; that the system is secure against a privileged operator; or that any human
process improved. Every one of those is out of scope, and a conformance badge implying otherwise is
the kind of claim a competent expert takes apart in one question.

A claim of conformance MUST cite version **and** profile. A claim without a profile is not a claim.
