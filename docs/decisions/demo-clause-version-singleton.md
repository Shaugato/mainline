<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The demo has ONE clause version, and the suite asserts that

**Decision.** `test_reads.py` addresses the clause-version read at the commit the blocking
check cites — `seed["commit_id"]` — and asserts the single, **origin** version the deployed
seed carries. A second clause version is **not** seeded.

**Status:** decided. Ruling §3.1 of `docs/leads/suite-green-plan.md`; corroborated
independently below before it was applied. **Owner:** W2 (suite-green wave).
**Date:** 2026-08-14. **Measured against:** `w3_demo_api_3b0aafc625f2`, built by applying
the 271-file migration chain plus `demo_world.sql` and `demo_permit.sql` through
`scripts/deploy/seed_demo.py`'s own applier.

---

## 1 · What was wrong

`verticals/mainline/apps/demo-api/tests/test_reads.py:95` asked the session-scoped `payloads`
fixture for `seed["commit_v2"]`. The fixture has never produced that name, and it refuses to
invent one — `_Seed.__missing__` raises with a diagnosis rather than a bare `KeyError`.

Because `payloads` is session-scoped and builds **all twelve** reads before any test in the
module runs, that one absent name failed the fixture during **setup** and turned every test
in the file into an **error**. That is the whole of the 63 errors: one name, sixty-three
nodes, and — critically — **every assertion in the file unexecuted for weeks behind it.**

`git log -S commit_v2` puts the name in at `5ddaa3a`, inside the *old* conftest, which built
a parallel world containing `_sha("commit", "clause-v1")` and `_sha("commit", "clause-v2")`.
The rewrite that made the fixture read the **deployed** seed deleted that world.
`test_reads.py` was not updated with it. **`commit_v2` is a survivor of a deleted fixture,
not a product decision.**

## 2 · Why this needed a higher burden of proof than usual

This change moves a **test** toward a **seed**. That is the exact direction the repository's
no-shortcut rule exists to police, because it is how a real defect becomes a permanent
invisible one. The rule is not "never move a test"; it is **ask which side is
authoritative**, and discharge the burden with an artefact that is not a party to the
dispute.

The tiebreaker this repository already uses, from
`tests/test_seed_covers_every_console_resource.py`:

> The console is the authority for which resources exist. It is the artefact a judge
> drives… Seed it, or delete it from `resources.ts`.

So the evidence below is drawn from the **console** and the **committed JSON Schemas** —
neither of which is the seed and neither of which is the test.

## 3 · The evidence, re-measured rather than inherited

### 3.1 No console path constructs a second clause version

Two code paths in the console request `clause_version`, and only two:

| path | how it builds `commit_id` | reaches a v2? |
|---|---|---|
| `features/gate/useGateData.ts:193` | `commit_id: subjectCheck?.commit_id` — the commit the **blocking check** cites | no |
| `features/diff/ClauseDiffScreen.tsx:107` | `commitId ?? route.params.get('commit') ?? DEMO_COMMIT` | no |

`DEMO_COMMIT` is `5f916282a2a3e5765f916282a2a3e5765f916282a2a3e5765f916282a2a3e576`. The
seeded database holds exactly two commits — `bbaa7455…c17` (root) and `9f12114d…a39`
(the clause commit). `DEMO_COMMIT` is **neither**; it is a placeholder that resolves to a
404 on any database, and it is not evidence that a second version exists.

A tree-wide search for `clause-v2`, `clause_v2` and `commit_v2` across
`console/src/` and `console/contracts/` returns **zero hits**.

Under the tiebreaker that ends it: **the console never tells a judge a second version
exists.**

### 3.2 A single-version clause is a first-class modelled state, not a degraded one

`features/diff/engine/build.ts::comparabilityOf()` returns `{ kind: 'origin_version' }` when
a version names no parent and none was carried. `ClauseDiff.tsx::ComparabilityNotice`
renders it under its own heading, **NO DIFF — ORIGIN VERSION**, with body text written for
precisely this case:

> This version names no parent, so there is nothing in this payload to compare it with.

It is a sibling of `parent_mismatch` and `parent_unresolved`, each with its own heading and
its own explanation. A modelled state with authored copy is a state the product intends to
render, not one it tolerates.

### 3.3 A v2 would contradict two rows the seed already carries

Measured on the seeded database:

* `mainline.clause.head_commit` = `9f12114d…a39` — the **v1** commit.
* `mainline.cr_clause` carries relation `'edits'` against that same commit.

The demo's narrative is *a change request PROPOSES to edit v1*. A v2 that already exists
makes the open change request propose an edit that has already happened.

### 3.4 The seed is complete as designed, not truncated

`demo_world.sql` §3 is titled "Two commits and the edge between them" and seeds
`root → clause-v1`. The DAG is whole. Nothing is missing from it.

### 3.5 What the one row actually is

```
mainline.clause_version → exactly 1 row
  gen 1 · commit 9f12114d…a39 · parent_version NULL
  control_delta 'introduce' · delta_basis 'lattice'
  anchor_set ['LOTO','ZERO_ENERGY'] · printed_label '7.3.2(b)'
```

## 4 · What was written

`test_reads.py:95` now passes `seed["commit_id"]` — the value `conftest._CHECK_SQL` reads off
`mainline.blocking_check`, which is the same column `useGateData.ts` reads. The fixture and
the console now name **one** commit.

`test_the_clause_version_reports_its_witnesses_as_a_positive_claim` was rewritten. **It kept
its name because it kept its promise**, and on this seed it makes that promise more sharply
than it did on the invented one:

* **`witnesses == []`, and explicitly not `None`.** `clause.schema.json`'s `delta_verdict`
  says *"`witnesses` may be null … which the console renders as WITNESS UNAVAILABLE. An
  empty array is a DIFFERENT claim: the emitter says there are none."*
  `engine/witness.ts` implements exactly three states —
  `witnesses === null ? 'unavailable' : witnesses.length === 0 ? 'asserted_none' : 'present'`
  — and `parts/WitnessTable.tsx` renders **WITNESS UNAVAILABLE** against **NO WITNESSES**.
  The assertion therefore says *which screen a judge sees*. A reader that stopped querying
  `mainline.delta_witness` and emitted `null` would still satisfy the schema, still render,
  and be wrong; this catches it.
* **`minimal is None` — the falsifiable one.** `read_clause_version` computes
  `all(minimal_flags) if minimal_flags else None`, and in Python **`all([])` is `True`**.
  Delete the guard and the payload claims the empty witness set is a *minimal unsatisfiable
  subset* — what the contract calls *"an unproven claim of minimality … worse than none"*.
  One assertion stands between a one-token edit and a demo asserting a proof it never ran.
* **Origin-ness asserted with both halves.** `version["parent_version"] is None` **and**
  `data["parent"] is None`. Only the pair distinguishes `origin_version` from
  `parent_unresolved`; asserting the second alone is satisfied by the broken state too. This
  is the "`[]` and `null` are different sentences" discipline applied to the parent.
* **The commit is cross-checked between two payloads**, against
  `payloads["blocking_checks"]…["commit_id"]` rather than a literal — mirroring
  `useGateData.ts`'s own addressing, and failing if a seed re-pointed one and not the other.
* **Provenance negatives:** `/parent` carries no chip (the reader adds it only when a parent
  was carried) and no `/delta/witnesses/*` chips exist. A chip beside nothing is worse than
  no chip.

**Nothing was deleted for being inconvenient.** The rewritten test asserts strictly more
than the one it replaced, and every assertion can fail.

## 5 · The same survivor, five more times

With `commit_v2` fixed the fixture built, the 63 errors went to **zero**, and **seven real
failures surfaced — the first time any assertion in this file had executed in weeks.** Five
were the identical archaeology: `test_reads.py` describing the parallel world of `5ddaa3a`.
Each was checked the same way before being moved.

| test | described (parallel world) | deployed seed | why the seed is authoritative |
|---|---|---|---|
| `…projected_counter_agrees…` | `state 'draft'`, `open_blocking 0` | `'dispositioned'`, `1` | `demo_permit.sql`'s header declares both, cites migration 0011's state alphabet, and says *"THE COUNTER IS NOT WRITTEN HERE"* |
| `…open_is_derived…` | `open False`, a `disposition_id`, `INC-W3-1` | `open True`, `None`, `DEMO-INC-0001` | `disposition = NO ROWS` by design — signing is beat 4. The old ref was named after the *worker* whose fixture wrote it |
| `…ancestry_resolves…` | `commit_chain [1, 2]`, 2 events, 2 blame edges | `[1]`, 1, 1 | `[1, 2]` is **two clause generations** — the same v1/v2 world, settled by the same ruling |
| `…silence_flags…` | `s 2`, `n 4`, one `below_tau` entry | `s 1`, `n 1`, no entries | `s == n` is `boundaryAtEnd`: nothing excluded, so an empty ledger is *required* for coherence. W1's committed `boundary_proof` is built for `s = n` and says so |
| `…audit_surface…` | 1 call, `pgwire`, `ok` | `[]` | the only INSERT into `mainline_meas.agent_action` in this tree is in a *test*; `CallLog.tsx` renders the empty log as a first-class claim |

Two assertions the old test made are **strengthened** rather than merely re-pointed:

* `open_blocking == re-derived == 1` is stronger than `== 0`. Zero is satisfied by a
  projection that never counted anything; **one** is satisfied only by a projection that
  counted the open obligation. That agreement *is* the product.
* `entries == []` and `event_edges == []` are asserted as claims with reasons, not as
  emptiness tolerated.

## 6 · The one that was NOT moved

**`test_the_disposition_carries_the_lattice_and_the_projected_requirements` still fails, and
its failing assertion is left byte-for-byte intact.** `mainline.defeater_option` holds zero
rows. Here the **seed is the wrong side**, and the evidence is again outside both parties:

* `0064_defeater_option.sql` — *"generated per check, so no global 'N/A' exists"*. There is
  no fallback anywhere, by design.
* `console/src/a11y/contract.ts` declares step `id: 'defeater'` —
  *"choose a defeater from the per-check vocabulary"*, `pointerOnly: false` — inside the path
  it asserts is *"the complete path from the refusal to the signature … with no pointer-only
  step"*. An empty vocabulary breaks that declared path at that step.
* `app/surfaces.ts` — *"a per-check defeater vocabulary with no global 'not applicable'"*.
* `types.generated.ts` declares `defeater_options` **non-optional**.
* **Nothing in this tree writes a `mainline.defeater_option` row** — not the seed, not a
  migration, not the runtime.

A judge who reaches the disposition screen cannot choose a defeater, and therefore cannot
sign. Weakening the assertion to `== set()` would have bought a green and converted a real,
currently-visible defect into a permanent invisible one. It is **reported** instead and
belongs to `demo_world.sql`'s owner.

The rest of that test — which asserted a *signed* disposition the seed deliberately does not
carry — was corrected, so the day the vocabulary is seeded the test goes green on that change
alone rather than needing a second archaeology pass.

## 7 · Which side moved, and why that side was the derived one

**A test moved toward a seed, in six places; a seventh was left failing.**

The seed is not authoritative *because it is the seed*. It is authoritative here because in
each case a **third artefact** — the console the judge drives, the committed JSON Schema the
console loads, or the migration that defines the table — agrees with it, and because the
value the test carried is traceable by `git log -S` to a fixture that was **deleted**. A
value inherited from a deleted fixture is derived; a value the console constructs and renders
is not.

Where that third artefact agreed with the **test** instead — the defeater vocabulary — the
test was left alone and failing. A rule that always moved the seed, or always moved the test,
would not be a rule.
