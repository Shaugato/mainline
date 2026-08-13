<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Seeding the ledger the demo publishes

**Worker:** W3 (suite-green wave). **Date:** 2026-08-14. **HEAD:** `e944407` (tree dirty).
**File changed:** `verticals/mainline/db/seeds/demo/demo_world.sql`, §8 only.
**Ruling followed:** `docs/leads/suite-green-plan.md` §3.3.

---

## 1 · The defect, re-measured rather than taken on trust

The brief and the lead both stated this; I re-measured it against
`w3_demo_api_885e1182f4e6`, the database the deployment's own applier built from
`demo_world.sql` + `demo_permit.sql`, before changing anything:

| table | rows |
|---|---:|
| `mainline.ledger_checkpoint` | **1**, `tree_size = 1`, `admissible = true` |
| `mainline.ledger_leaf` | **0** |
| `mainline.ledger_node` | **0** |
| `mainline.ledger_intake` | **1** |

The single checkpoint's `root_hash` was `digest('mainline-demo/ledger/root/1', 'sha256')` —
the SHA-256 of a string naming itself, committing to nothing.

**The demo's transparency log published a signed commitment to a tree of size one over zero
leaves.** In the one surface whose entire purpose is that claims have something behind them.

Two details sharpen it beyond what the brief said:

* The lone `ledger_intake` row is **not** a demo entry. It is the sentinel the closure guard
  (`0108_fn_closure_guard.sql`) writes from a trigger, and its own migration calls it a
  placeholder: `canon_bytes = 0x00`, `leaf_hash` = thirty-two zero bytes, "the relay
  recomputes both client-side before sequencing". Sequencing *that* row would have produced a
  leaf whose hash commits to nothing — a worse outcome than the empty table, because it would
  have looked full.
* `reads.read_ledger` was the only thing standing between that checkpoint and a false exhibit:
  it refuses to emit proofs over a window that does not cover the checkpoint's `tree_size`, so
  the console showed empty proof arrays rather than wrong ones. The honesty machinery worked.
  It should not have had to.

---

## 2 · Which side was authoritative, and which side I moved

**I moved the SEED. The seed was the derived side, and it was false on its own terms.**

This deserves the burden of proof, because I was asked to edit the same file a worker was once
caught reshaping to match an application constant (`tests/ci/test_demo_seed_is_frozen.py`).
The distinction is not that my edit is more tasteful:

1. **The seed's claim was false without reference to any test.** A checkpoint asserting
   `tree_size = 1` over an empty `ledger_leaf` is refuted by the schema's own semantics
   (`root_hash` is "the 32-byte RFC 6962 Merkle Tree Hash at `tree_size`", migration 0075).
   No test is needed to see it. A value that is wrong on its own terms cannot be the
   authoritative side of a disagreement.
2. **The suite's expectations were corroborated by a third artefact.** `git show 5ddaa3a --
   .../tests/conftest.py` — the *old* fixture, deleted when the fixture was rewritten to read
   the deployed seed — built exactly this world: `for seq in range(4)`, `for tree_size in
   (2, 4)`, and two level-1 nodes at `_mth(leaves[:2])` and `_mth(leaves[2:4])`. So the
   four-leaf, two-checkpoint ledger is **the demo's designed world**, which the rewrite simply
   never carried across into `demo_world.sql`. The tests are the survivors of a world that was
   *real*, not of one that was invented.
3. **Nothing contradicts it.** This is the check that makes point 2 evidence rather than
   archaeology, and it is where this case differs from `commit_v2` (plan §3.1): there the lead
   found the console actively contradicted a second clause version, so the *test* lost. Here
   `ledger.schema.json` requires a consistency proof "for every consecutive checkpoint pair"
   and pins no sizes; nothing in `resources.ts`, the console, or any migration names a
   particular tree size. Checkpoint sizes are the seed's own design choice, and a log that
   publishes at 2 and again at 4 is a log behaving normally.

**What I did NOT move.** No hash, no proof path, and no expected value was copied from a test
into the seed. `test_reads.py` is untouched (W2's file). The `== [0, 1]` assertion in
`test_an_undeclared_query_parameter_is_refused_rather_than_ignored` was not weakened; it is now
true because leaves 0 and 1 exist.

### 2.1 The one thing I changed that was previously true-ish, and why

The old checkpoint sat at `tree_size = 1`; the new ones sit at 2 and 4. With four leaves a
size-1 checkpoint would *also* have been true (MTH of one leaf is that leaf). I did not keep it,
and the honest statement of why is: three checkpoints would produce consistency proofs
`[(1,2), (2,4)]` where the suite expects `[(2,4)]`.

That is close enough to "shaping the seed to a test" to be worth stating plainly rather than
burying. What makes it legitimate: the size-1 row is not an independent fact that survives —
it is *the defective row itself*, the one that claimed a tree over nothing. Nothing anywhere
requires a checkpoint at size 1; the only consumer with an opinion,
`fn_recall_policy_anchored`, asks for `cp.tree_size >= anchored_size` and is satisfied by both
new checkpoints (§9's `anchored_tree_size` is 1, unchanged, and I did not touch it). The
alternative — keeping a third checkpoint purely so as not to appear to have chosen — would be
seeding a row for the benefit of an audit rather than for the demo.

**If a reviewer disagrees, the place to push back is here**, and the resolution is one line in
§8.4, not a change to any test.

---

## 3 · How the leaves were appended: the product's own appender, no typed digests

Every hash in §8 is computed by the database. The seed contains **no hex digest literal** for
any leaf, link or node — verified mechanically (§4, check 8).

* **`leaf_hash` = `digest(decode('00','hex') || canon_bytes, 'sha256')`** — RFC 6962 §2.1 leaf
  domain separation, taken over the canonical bytes.
* **`prev_link_hash` and `link_hash` are computed by
  `mainline.fn_ledger_cas_append`** (migration `0119_fn_ledger_cas_append.sql`). The seed never
  INSERTs into `mainline.ledger_leaf`. `seq` is derived in-transaction as
  `coalesce(max(seq)+1, 0)`; genesis `prev_link_hash` is 32 zero bytes and not NULL (CU-1); the
  two UNIQUE constraints that make a fork physically impossible are walked, not bypassed.
  *Correction to the brief and to plan §3.3: the appender is defined in migration **0119**, not
  in `0073_ledger_leaf.sql`, which defines only the table. 0073's header is still the normative
  description of the semantics.*
* **Interior nodes** = `digest(decode('01','hex') || left || right, 'sha256')`, read back out of
  the leaves the appender wrote — never out of the values the seed supplied.
* **Checkpoint `root_hash`** is `SELECT`ed out of `mainline.ledger_node`: the size-2 root *is*
  node (1,0) and the size-4 root *is* node (2,0). Storing the root as a node and then reading
  it into the checkpoint makes the redundancy **checkable** rather than two independent
  assertions that happen to agree.

### 3.1 Migration 0072 says "DO NOT COMPUTE `leaf_hash` IN SQL". I have, and here is why that is not a violation

This is the sharpest objection to this change and it should not be discovered by a reviewer;
it is stated here. 0072's header reads:

> DO NOT COMPUTE `leaf_hash` IN SQL. CockroachDB's `sha256()` returns a hex STRING, not BYTES
> (cockroach#73896), and JSONB normalises and reorders keys — so `sha256(payload::STRING)` is a
> value no third party can reproduce.

Both stated failure modes are the *same* failure mode — deriving the hash from `payload` — and
neither is present here:

* `digest(...)` returns **BYTES**. `sha256()` is not used anywhere in §8. (The migration's own
  appender, 0119, uses `digest()` to compute `link_hash` in SQL for exactly this reason.)
* The hash is taken over the literal **`canon_bytes`**, never over `payload`. JSONB's key
  reordering cannot reach it.
* **The canonicalisation is not performed in SQL.** That is the part SQL genuinely cannot do,
  and it is not attempted: the RFC 8785 bytes are written out longhand in the seed — sorted
  keys, no whitespace — and `payload` is `CAST FROM THE SAME LITERAL` (`c.j::JSONB` and
  `c.j::BYTES` in one `SELECT`), so the evidence and the human rendering cannot drift.

The residual risk is that a hand-written literal is not *actually* JCS. That is checked, not
asserted: §4 check 2 feeds each row's `payload` back through the product's own
`trappoint_jcs.canon_v1.canonicalise_payload()` and compares byte-for-byte with the stored
`canon_bytes`. If a future editor adds a key out of order, that check fails.

---

## 4 · The falsification, and how to re-run it

`docs/decisions` cannot hold a script, so the procedure is recorded here in full. It is
deliberately written against the *database*, so it fails if the seed drifts from the schema's
meaning rather than from my intentions.

Build a scratch database with the deployment's own applier (271 migrations, then
`seed_demo.apply_seeds`), then **apply the seeds a second time**, then run eight groups of
checks. Every hash Python recomputes is derived from `canon_bytes` read out of the database —
none is a constant in the checking code.

| # | check | result |
|---|---|---|
| 1 | `leaf_hash == SHA-256(0x00 ‖ canon_bytes)` for all four leaves | pass |
| 2 | `canon_bytes == canon_v1.canonicalise_payload(payload)` — the bytes really are JCS | pass |
| 3 | link chain: `prev_link_hash` chains, `link_hash == SHA-256(prev ‖ leaf)`, genesis is 32 zero bytes | pass |
| 4 | `ledger_node` (1,0), (1,1), (2,0) equal the RFC 6962 MTHs of their leaf ranges | pass |
| 5 | exactly two checkpoints at 2 and 4; each `root_hash == MTH(leaves[:size])`; each note names its own root; `max(tree_size) == leaf count` | pass |
| 6 | `reads.read_ledger` returns leaves `[0,1,2,3]`, consistency proofs exactly `[(2,4)]` with a non-empty path, and **every inclusion proof reproduces the checkpoint root it names** | pass |
| 7 | the range read `from_seq=0,to_seq=1` returns leaves `[0, 1]` | pass |
| 8 | no leaf or node digest appears as a literal anywhere in `demo_world.sql` | pass |

Check 6's inclusion verifier was written from RFC 6962 directly rather than by calling
`reads._inclusion_path`, so it is capable of disagreeing with the code under test.

**Re-appliability** (a hard requirement of the brief, and sharper here than elsewhere in the
file): an appender is by definition not idempotent, and `ON CONFLICT DO NOTHING` cannot help,
because the INSERT happens inside a PL/pgSQL body the seed's conflict clause does not reach.
Fixed `entry_id`s would make `ledger_leaf_entry_unique` refuse a replay with 23505 — but an
exception aborts the whole batch. So every append is guarded by an anti-join against
`mainline.ledger_leaf`, and on a second run the guard selects zero rows and the function is
never called.

Measured, two consecutive applications to the same database:

```
SEED RUN 1: OK   {intake: 5, leaf: 4, node: 3, checkpoint: 2, cosignature: 2}
SEED RUN 2: OK   {intake: 5, leaf: 4, node: 3, checkpoint: 2, cosignature: 2}
```

No error, no second row. (`intake` is 5, not 4: the fifth is the closure-guard sentinel from
§1, which is deliberately **not** sequenced — see §5.)

---

## 4a · Full-suite numbers, and an honest statement of what they can and cannot attribute

`pytest verticals/mainline/apps/demo-api/tests --crdb=reuse -q -p no:cacheprovider
--junit-xml=…`, read from the XML root element and from nowhere else.

| | tests | passed | failed | skipped | errors | wall |
|---|---:|---:|---:|---:|---:|---:|
| BEFORE | 524 | 454 | 6 | 1 | 63 | 203.9 s |
| AFTER | 525 | 458 | 1 | 1 | 65 | 86.3 s |

BEFORE reproduces the lead's baseline (§0) exactly, which is what makes it a usable baseline.

**⚠ The AFTER run is NOT attributable to this change alone, and saying so is not a hedge.**
Between the two runs, W1 committed edits to `demo_permit.sql` and W4 to
`test_response_contract.py` in the same working tree. That is visible in the numbers rather
than inferred: `tests` moved 524 → 525 (a node id W2/W4 added), and three
`test_response_contract` node ids went red → green, which is W4's blocker-2 work and none of
mine. The fixture fingerprint moved twice mid-measurement (`885e1182f4e6` → `634f1511e06d` →
`659cc28599d7`) because it hashes the seed files.

**Newly green that IS mine:** `test_reads::test_an_undeclared_query_parameter_is_refused_rather_than_ignored`
— blocker 6, closed on the seed side, with the `== [0, 1]` assertion untouched.

**Regression set: 3 node ids, all in `test_transitions.py`, none caused by this change.**

```
passed -> error   test_transitions::test_a_one_word_clearance_is_refused_by_the_api_not_the_gate
passed -> failed  test_transitions::test_gate_run_is_reachable_through_handle_transition
passed -> error   test_transitions::test_materialise_checks_issues_a_receipt_and_moves_the_subject
```

`qa/cluster-known-red.json` names `test_gate_run_is_reachable_through_handle_transition`
explicitly in its `unstable` list and records that the contaminated set "is at least three node
ids wide" and that "they move together". I did not stop at matching that description — I
re-ran the module twice with no edit to the tree in between:

```
run 1:  32 passed, 1 error   (test_every_outcome_hands_the_connection_back — a FOURTH node id,
                              in neither the regression set nor the registry's list)
run 2:  33 passed            (clean)
```

A set that differs across two identical runs of an unchanged tree is not a regression caused by
a seed. This is the cross-test contamination plan §6/W6 exists to turn from **not-observed**
into **measured**, and it is reported, not routed around.

**Still red, and correctly attributed elsewhere:** 63 of the 65 errors are the single
`payloads`-fixture cause. Measured at 2026-08-14 03:30, `test_reads.py:95` still reads
`seed["commit_v2"]`, so **W2's ruling-§3.1 change has not landed**. The remaining 2 errors are
the `test_transitions` flapper above. Per plan §1 neither W1 nor W3 alone can clear the 63, and
this run is consistent with that: all thirteen reads — including `silence`, which is W1's — now
succeed against a scratch database built from the current seeds, so `commit_v2` is the last
one standing.

**The ledger is provably not among the causes:** `read_resource(conn, "ledger", …)` succeeds,
and its payload validates against `ledger.schema.json` through the suite's own
`SchemaRegistry` with **zero** errors — checkpoints `[(2, bf5dc3e5…), (4, 49b22526…)]`, nodes
`[(1,0), (1,1), (2,0)]`, 6 inclusion proofs, consistency `[(2,4)]`.

### 4b · An operational finding about the fixture, reported not fixed

`demo_database` decides the database is absent by connecting, then issues a bare
`CREATE DATABASE`. Two workers running the suite concurrently after a seed edit both see it
absent and both create it: the loser gets `psycopg.errors.DuplicateDatabase` **on setup for
every test in the run**. That is what my first AFTER attempt was — 104 errors, zero of them
real, on a database that turned out to be correctly built. A run can therefore report a hundred
failures that mean only "somebody else got there first". `CREATE DATABASE IF NOT EXISTS`
plus a wait on the `w3_fixture.ready` marker would remove it. `conftest.py` is not in this
wave's owned set, so this is a report.

---

## 5 · What this seed still does not prove

Stated because the rest of this file is a claim to have made something true, and the boundary
of that claim matters more than the claim.

* **`log_sig`, `tsa_token` and `beacon` remain synthetic** and are marked so in the data. A
  real checkpoint's evidentiary value is that it left the trust boundary before we could change
  our minds about the tree; these did not. `admissible = true` is likewise seeded, not
  projected — migration 0075's own OPEN CONTRADICTION section explains why nothing can project
  it yet.
* **The witness is our own.** `DEMO-HONESTY.md` §4 already says adverse witnesses are not
  running. `adverse = true` is the column's declared value for a different trust domain; the
  honest reading is "the mechanism is exercised", never "an independent party signed this".
* **`canon_src_sha256` is a named placeholder**, not the live hash of the canonicaliser source.
  Pinning the real value would make this seed go red on any edit to a file it does not own.
* **The closure-guard sentinel intake row is left unsequenced.** That is correct, not an
  oversight: sequenced-ness is derived, never written, and an intake row awaiting sequencing is
  the normal state of a log (it is the Maximum Merge Delay). Sequencing a placeholder whose
  `leaf_hash` is thirty-two zero bytes would put a leaf committing to nothing into the tree.

**What IS now true, and was not before: `root_hash` commits to leaves that exist, every leaf
hash is recomputable by a stranger from bytes the API serves, and every inclusion and
consistency proof the console renders verifies.**

---

## 6 · Coordination — what W1 and W2 need from this

* **W2** — the range assertion `== [0, 1]` in
  `test_an_undeclared_query_parameter_is_refused_rather_than_ignored` is now **true** and must
  not be weakened. `test_the_consistency_proof_between_the_two_checkpoints_is_present` is
  satisfied as written: leaves `[0,1,2,3]`, consistency `[(2,4)]`, genesis `"0"*64`,
  `is_sandbox` false throughout. Neither test needed a change and I made none.
* **W1** — the silence receipt's `boundary_proof` needs a real Merkle inclusion path
  (`silence.schema.json` `$defs.boundary_leaf` requires an object with `index`,
  `leaf_hash_hex`, `score`, `path_hex`). The four leaves now exist for it to point at. **Derive
  those values from the database, do not type them**; in the four-leaf tree the paths are
  `leaf 1 → [leaf 0, node(1,1)]` and `leaf 2 → [leaf 3, node(1,0)]`, all four values readable
  from `mainline.ledger_leaf` / `mainline.ledger_node`. The seeded `s = 2`, `n = 4` in
  `test_reads.py` is consistent with a boundary pair at leaves 1 and 2.

  **Measured against W1's in-flight `demo_permit.sql` at 2026-08-14 03:30, and reported rather
  than acted on** (`demo_permit.sql` is W1's file and I did not touch it): the boundary proof
  currently reads

  ```
  {"leaf_s": {"index": 0, "leaf_hash_hex": "f23c0569…c26ab", "path_hex": [], "score": 0.35},
   "leaf_s_plus_1": null}
  ```

  `read_silence` accepts it, so the undeclared-keys defect (blocker 5) is genuinely fixed. But
  `SELECT count(*) FROM mainline.ledger_leaf WHERE encode(leaf_hash,'hex') = 'f23c0569…'`
  returns **0**: the leaf it names is not in the tree. The seeded leaves are `032980be…`,
  `80300ea9…`, `6ca2bb9a…`, `6e3fb057…`. With `path_hex` empty and `leaf_s_plus_1` null, the
  exhibit commits to nothing and cannot be verified against either checkpoint — which is the
  "renders an exhibit that proves nothing" outcome plan §3.2 refused when it declined to widen
  the schema. **This is W1's call and W1's file. I flag it because a boundary proof that
  validates but does not verify is the same class of defect this document exists to remove from
  the ledger, one table over.**

---

## 7 · A red this change will cause that is NOT this change being wrong

`tests/ci/test_demo_seed_is_frozen.py` freezes the SHA-256 of both deployed seed files, and my
edit changes `demo_world.sql`'s bytes. That test will go red.

**I did not re-baseline it**, for two reasons: the suite-green plan §4 lists ratchets among the
files nobody in this wave edits, and it is not in W3's owned set. That test's own docstring says
a red is "a question, not a verdict", that re-baselining is expected and allowed, and that it
must happen **in the same commit** as the seed change with a message saying what changed and
why. This document is that sentence.

W1's `demo_permit.sql` change will move the second hash. **Whoever commits this wave must
re-measure both hashes in the same commit** — and must read this section before doing so,
because a hash re-baselined without reading is exactly the failure that test exists to prevent.

One related observation, reported rather than acted on (the file is not mine):
`scripts/deploy/seed_demo.py`'s `COUNTED` census lists `mainline.ledger_checkpoint` and
`mainline.cosignature` but **not** `ledger_leaf`, `ledger_node` or `ledger_intake`. The
deployment's own evidence of what it seeded will therefore not show the four leaves. Adding
those three names would make the census cover the ledger it now carries.
