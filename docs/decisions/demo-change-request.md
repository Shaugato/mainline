<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The demo world gains its second gated subject

**Worker:** `w1-change-request-seed` · **Measured 2026-08-13 on TRAPPOINT**, HEAD `073dfea`
· **Node:** local CockroachDB CCL **v26.2.5** on `127.0.0.1:26257`
· **Interpreter:** `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`
· **Ruling implemented:** `docs/leads/demo-suite-plan.md` §1.1
· **Scratch database:** `w_w1_change_request_seed` (271 migrations, 0 failures, both seed files OK)

`verticals/mainline/db/seeds/demo/demo_world.sql` now carries a change request, the clause
edge that says what it proposes, its precursor obligation and its first chain event.
`verticals/mainline/apps/demo-api/tests/conftest.py` reads its identifier back out of the
database with a `_sole(...)` query and mints nothing.

---

## 1 · The defect, measured

`verticals/mainline/apps/demo-api/tests/test_reads.py:90` asks for `seed["cr_id"]`.
`_Seed.__missing__` (`tests/conftest.py:414`) refuses, and because `payloads`
(`test_reads.py:107`) is **session-scoped**, that one `KeyError` errored **63** of the 444
results in the demo-api suite. From `out/demo-suite-baseline.xml`, verbatim:

> `'cr_id' is not an identifier the deployed demo seed produces. … It offers: check_id,
> clause_gen, clause_uuid, commit_id, countersigner_credential_id, countersigner_sub,
> doc_id, event_id, permit_external_ref, permit_id, permit_state, policy_version,
> receipt_id, run_id, signer_credential_id, signer_sub, silence_receipt_id, site_code,
> site_id, site_role.`

Twenty names, and no `cr_id` among them. I checked the cause rather than inheriting it:

```
$ grep -c 'change_request\|cr_id' verticals/mainline/db/seeds/demo/demo_world.sql
0
$ grep -c 'change_request\|cr_id' verticals/mainline/db/seeds/demo/demo_permit.sql
0
```

**Neither seed file mentions the subject at all.**

## 2 · Why the ruling is SEED THE ROW and not ASSERT THE 404

The deciding evidence is outside the test suite. I confirmed each line myself:

| layer | file | what it declares |
|---|---|---|
| the console resource | `apps/console/src/data/resources.ts:84-90` | `declare('change_request', 'GET', '/v1/change-requests/{cr_id}', …, 'kernel', 'The second gated subject. The repository is the protected branch; the permit is one of its refs.')` |
| the console's resource list | `apps/console/src/data/resources.ts:224` | `'change_request'` ∈ `RESOURCE_KEYS` |
| the committed contract | `apps/console/contracts/change-request.schema.json` | committed; `$id` `…/contracts/1.0/change-request.schema.json` |
| the route | `apps/demo-api/src/mainline_demo_api/app.py:213` | `Route("GET", "/v1/change-requests/{cr_id}", "change_request")` |
| the reader | `apps/demo-api/src/mainline_demo_api/reads.py:513` | `read_change_request(...)` |
| the table | `db/migrations/0051_change_request.sql` | `CREATE TABLE mainline.change_request` |
| the transition alphabet | `db/migrations/0017b_subject_transition_seed.sql:38-46` | nine legal `change_request` edges |

Seven layers of product exist for a subject the demo world did not contain. A judge who
clicked the resource got a **404**. Asserting that 404 would have made the suite green while
certifying that the demo's second gated subject is furniture — the same category of act as
reshaping a seed to match an application constant, which is how beat 4 reached a judge behind
291 green tests. It moves a defect from *visible* to *documented-as-intended*.

**This change is the opposite of that shortcut, and the difference is checkable:**

1. **A subject the product declares is being added; no value is reshaped to match code.**
   Every identifier below is a fresh literal in the `dec0de00-…` family this file already
   uses. Nothing in `verticals/mainline/apps/demo-api/src/` computes any of them, and no
   value in the seed was chosen to equal anything in Python.
2. **The fixture still mints nothing.** `_Seed.__missing__` is byte-identical to what it was;
   its instruction — *"Seed it in `demo_world.sql` so the deployment carries it too, or assert
   the 404"* — is being obeyed on the branch it names first.
3. **The deployment carries it.** `scripts/deploy/seed_demo.py` applies `demo_world.sql` to
   CockroachDB Cloud, so this row reaches the judge's URL and not only the laptop. That is why
   the identifier is a stable literal and not `gen_random_uuid()`: the deployed demo and the
   fixture must name the same row. (`CREATE SEQUENCE`, `nextval`, `SERIAL` and
   `unique_rowid()` are banned on this platform, so a generator was never an option either.)

The 404 is not lost: W2 adds a separate test that an *unknown* `cr_id` is answered 404.

## 3 · The rows I seeded

`demo_world.sql` §10, after the recall policy and before the closing census:

| table | identifier / key | value |
|---|---|---|
| `mainline.change_request` | `cr_id` | `dec0de00-000c-4000-8000-000000000001` |
| | `site_id` | `dec0de00-0001-4000-8000-000000000001` — **the site the permit already uses**; no second site was invented |
| | `external_ref` | `DEMO-MOC-0001` |
| | `ref_name` | `refs/changes/demo-0001` |
| | `target_ref` | `refs/heads/main` — the protected branch, which is the ref the seeded commit DAG is on |
| `mainline.cr_clause` | `(cr_id, clause_uuid, relation)` | the seeded clause version, `relation = 'edits'` |
| `mainline.blocking_check` | `check_id` | `dec0de00-000d-4000-8000-000000000001`, `subject_kind = 'change_request'`, `cr_id` set, **`permit_id` NULL** |
| `mainline.cr_event` | `(cr_id, seq)` | `seq 1`, `draft → checks_materialised` |

**`permit_id` is NULL on that obligation, and that is load-bearing.** `mainline.blocking_check`
carries both `permit_id` and `cr_id` (`0058_blocking_check.sql:70-71`, `CONSTRAINT
exactly_one_subject CHECK ((permit_id IS NULL) <> (cr_id IS NULL))`), and
`tests/conftest.py:499`'s `_CHECK_SQL` is `FROM mainline.blocking_check WHERE permit_id = %s`
under `_sole`, which demands exactly one row. Measured on the scratch database after seeding:
`SELECT count(*) FROM mainline.blocking_check WHERE permit_id = 'dec0de00-0006-…'` → **1**.

Two other `_sole` traps were checked the same way and are clear:
`SELECT count(*) FROM mainline.permit` → **1** (no second permit), and
`SELECT count(*) FROM mainline.person` → **2** (no third person — the change request's actor is
`demo.signer`, who the world already has, so `_OTHER_PERSON_SQL` still has exactly one answer).

### The state I chose, and why

**`checks_materialised`, with one open blocking obligation.** `draft` would have been one
`INSERT` and would have said nothing: a subject whose gate has never closed demonstrates no
gate. The console's own description of the resource is *"The second gated subject. The
repository is the protected branch; the permit is one of its refs."* — so the change request has
to be gated on screen or the sentence is decoration.

The story the data now tells is the true one: the same 2019 precursor (`DEMO-INC-0001`) whose
blame closure armed the permit's obligation also reaches the clause version this change request
proposes to **edit**, so the same closure arms an obligation here, and nobody has disposed of
it. `('change_request', 'draft', 'checks_materialised')` is one of the nine edges
`0017b_subject_transition_seed.sql` seeds, so the `cr_event` row is legal by foreign key rather
than by permission.

### What the seed supplies, and what it must not

`0051_change_request.sql`'s banner declares `open_blocking`, `open_residue`, `open_conflicts`
and `site_role` **projected** with `@on_missing raise`, so the seed supplies **none of the three
counters**. Measured after applying the block: `open_blocking = 1`, `gate_epoch = 1`, both
written by `mainline.fn_check_materialised` (`0101`, welded to `blocking_check` by `0121`) when
the obligation was inserted — the same trigger, on the same path, as the permit's. Likewise
`severity` and `virulence` are supplied as `0` / `'routine'` and are overwritten by
`fn_check_project` (`0100`, welded by `0120`); the row reads back **severity 4, virulence
`blood_major`**, projected from the closure `demo_world.sql` §6 wrote.

`site_role` **is** supplied, and that is a measurement rather than a preference:
`0109_fn_site_role.sql`'s own header says it ships *"DELIBERATELY UNWELDED IN THIS BAND"*
because the kernel's acyclicity ruling reserves a gated subject's trigger slot for the merge
gate, and `grep -l fn_site_role db/migrations/*.sql` returns only `0020a`, `0109`, `0181b` and
`0181f` — **no `CREATE TRIGGER` welds it to `mainline.permit` or `mainline.change_request`.**
The column is `NAME NOT NULL` with no default, so an INSERT that omitted it would be `23502`.
`demo_permit.sql:88` supplies it for the permit for exactly the same reason. The value is
`'demo_site'`, which is `mainline.site.site_role` — the authority the unwelded function would
have read.

### The constraints on `mainline.change_request`, all satisfied

`cr_external_ref_unique (site_id, external_ref)` — one change request, one `DEMO-MOC-0001`.
`cr_epoch_target (cr_id, gate_epoch)` — one row. `cr_ctr_nonneg` — 1/0/0. `cr_ledger_nonneg` —
`head_seq = 1`, `gate_epoch = 1`. The four named refusals
(`cr_gate_closed_when_merged`, `cr_identity_conserved_when_merged`,
`cr_conflicts_resolved_when_merged`, `cr_merge_evidence`) are all of the form
`state <> 'merged' OR …`, so they are vacuous in `checks_materialised` — **and they are exactly
the four the read surface reports**, read out of `pg_constraint` rather than a list in Python.

## 4 · What I measured after seeding

Against the scratch database `w_w1_change_request_seed` (chain + both seeds + the new block):

* **The block applies twice with no error and no second row.** `ON CONFLICT DO NOTHING` on the
  three plain INSERTs; `INSERT … SELECT … WHERE NOT EXISTS` on `cr_event`, because
  `fn_cr_event_chain` is a BEFORE INSERT trigger that can raise and a BEFORE trigger runs before
  conflict resolution — the same rule this file already states above `clause_version`. The
  `UPDATE` is guarded `AND head_seq < 1`.
* **`read_change_request` answers, and its payload satisfies the committed contract.** Validated
  with the suite's own `SchemaRegistry` against
  `apps/console/contracts/change-request.schema.json`: **`SCHEMA ERRORS: none`**.
* The payload reads
  `state: "checks_materialised"`, `head_seq: 1`, `gate_epoch: 1`,
  `counters: {open_blocking: 1, open_residue: 0, open_conflicts: 0}`, `merged_commit: null`,
  and four constraints named by the catalog.

## 5 · What I did NOT touch, and one thing I found and left alone

* `_Seed.__missing__` is **byte-identical**. I am obeying its instruction, not editing it.
* No existing value in `demo_world.sql` was changed. The block is additive.
* `tests/conftest.py` still contains no SHA-256 helper and no literal restated from the seed:
  `_CR_SQL` is an unfiltered `SELECT … FROM mainline.change_request` under `_sole`, exactly as
  `_PERMIT_SQL` is for the permit, so "exactly one change request" is an assertion about the
  whole database rather than about whichever row a scan reached first.

**Found and NOT touched — reported to the lead instead.**
`tests/test_reads.py:95` asks for `seed["commit_v2"]`, which the fixture has never produced
either. `git log -S 'commit_v2'` shows the name entered at `5ddaa3a`, in the *old* conftest that
built a parallel world with two clause versions (`_sha("commit","clause-v1")` and
`_sha("commit","clause-v2")`); the rewrite that made the fixture read the deployed seed deleted
that world and `test_reads.py` was not updated. The deployed seed has **one** clause version, at
the commit `_CHECK_SQL` already publishes as `commit_id`, so the authoritative fix is
`seed["commit_id"]` at `test_reads.py:95` — **W2's file, not mine.** I did not add a
`commit_v2` alias to the fixture: naming the gen-2 commit `commit_v2` would make the fixture
describe a second clause version that the deployed world does not have, which is the
parallel-world defect in miniature. Until W2 lands that one-token change the `payloads` fixture
still raises on setup and the 63 errors stand — see §6.

## 6 · Suite numbers, whole demo-api suite, `--crdb=reuse`

Both runs are read from the junit XML root element, not from a terminal scroll.

| run | tests | passed | failed | skipped | errors | seconds |
|---|---:|---:|---:|---:|---:|---:|
| before — `out/demo-suite-w1-change-request-seed-before.xml` | 445 | 378 | 3 | 1 | 63 | 1530.29 |
| after — `out/demo-suite-w1-change-request-seed-after.xml` | 445 | 379 | 2 | 1 | 63 | 1546.18 |

**No previously-passing test regressed. The regression set is empty**, computed by differencing
the two XMLs test-id by test-id, and the 63 errors are the *same* 63 tests in both runs. One test
went from failing to passing —
`test_reads::test_health_reads_the_deploy_chain_marker_when_the_database_has_one`, which failed in
the "before" run with `InvalidCatalogName: database "w5_deploy_chain_marker" does not exist`.
That is a concurrent worker's scratch database disappearing under it, not my change.

**The baseline is 445/378/3/1/63 and not the plan's 444/375/5/1/63, because the tree moved under
me.** This wave's other workers share the repository and the cluster: between the lead's baseline
and mine, `test_demo_guard_anonymous::test_the_four_posts_are_refused_…` and both
`test_refusal_row_factory` failures had already gone green, one test had been added (444 → 445),
and `out/` had acquired `demo-suite-w3-raising-branch-*.xml` and `demo-suite-w4-*.xml` written
while my own runs were in flight. My first attempt at a baseline was measured while my scratch
database was building on the same node and reported 444/372/7/1/64 — two extra failures and one
extra error, all in the "a refused transaction persisted nothing" family. **I discarded it and
re-measured rather than reporting the noisy number**, and both figures in the table above are
from runs with no build of mine on the cluster. On a shared node the comparison that means
something is the before/after **set difference**, not the totals.

**The 63 errors do not fall in the real tree, and the reason is not this change.** They fall the
moment `test_reads.py:95` stops asking for `commit_v2` — the §5 finding, in W2's file. Measured
with that one token changed to `commit_id`, then reverted:

```
$ pytest verticals/mainline/apps/demo-api/tests/test_reads.py --crdb=reuse
   74 tests · 62 passed · 12 failed · 0 errors · 244.87 s
   (out/w1-probe-test-reads.xml)
```

**0 errors, down from 63.** `test_every_read_satisfies_its_committed_contract[change_request]`
**passes** — the payload the real reader produces from the real seeded row satisfies the console's
committed schema — and so do
`test_the_change_request_gate_is_smaller_and_says_so`,
`test_every_read_survives_the_clients_own_post_conditions[change_request]`,
`test_every_provenance_pointer_addresses_something_real[change_request]` and
`test_no_read_silently_drops_a_provenance_claim[change_request]`. The 12 remaining failures are
content assertions this module has been carrying all along, invisible while the fixture errored on
setup — `control_delta 'strengthen'` where the seed says `introduce`, `assert 1 == 2` where the
module expects two clause versions, `INC-W3-1`, empty ledger proofs, the 10 s `/v1/health`. Every
one of them is W2's, and none is caused by the change request. The probe was applied to
`test_reads.py`, measured, and reverted; the file is byte-identical afterwards —
`sha256 4247e3bd…`, 45 274 bytes, `git diff` empty.

## 7 · Falsification

Both halves were falsified against real databases, not argued.

**The fixture depends on the seed.** The new `_identifiers` was run against
`w3_demo_api_123396ff6486`, a fixture database built from the seed *before* this change, and
against `w3_demo_api_885e1182f4e6`, built from it *after*:

```
SEED WITHOUT the change request: REFUSED -> mainline.change_request — the demo's second gated
   subject: the seeded database holds 0 such rows where exactly one is required. This database
   was built by applying demo_world.sql, demo_permit.sql out of …/db/seeds/demo; if those files
   no longer produce this row then the DEPLOYED demo no longer carries it either, and that is
   the defect — not this assertion.
SEED WITH    the change request: cr_id = dec0de00-000c-4000-8000-000000000001
                                 cr_state = checks_materialised
                                 cr_external_ref = DEMO-MOC-0001
```

So the value is not obtainable without the row, which is the property that separates a read-back
from a mint.

**The seed depends on the fixture reading it.** Without the `_sole(_CR_SQL, …)` call the seeded
row is invisible to the suite and `seed["cr_id"]` raises the original
`KeyError: 'cr_id' is not an identifier the deployed demo seed produces` — that is precisely the
measured "before" state, 63 errors, in the table above.

Neither half passes without the other.
