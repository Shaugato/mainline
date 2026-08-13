<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The demo silence receipt's boundary proof — the contract is authoritative, the seed was wrong

**Decision date:** 2026-08-14 · **Worker:** W1 (suite-green wave) · **Ruling:**
`docs/leads/suite-green-plan.md` §3.2, adopted unchanged.
**Files changed by W1:** `verticals/mainline/db/seeds/demo/demo_permit.sql` (§2's statement and
the IDEMPOTENCE block that documents it) and this document. Nothing else.

---

## 1 · The defect, as measured

`demo_permit.sql` seeded `mainline_meas.silence_receipt`
`dec0de00-000a-4000-8000-000000000001` with

```json
{"synthetic": true, "leaf_s": [], "leaf_s_plus_1": [],
 "source": "verticals/mainline/db/seeds/demo/demo_permit.sql"}
```

and `reads.read_silence` refused to render it (`reads.py:1904`, `Unrepresentable` → 409):

```
boundary_proof carries ['leaf_s','leaf_s_plus_1','source','synthetic'] where the contract
declares ['leaf_s','leaf_s_plus_1']; undeclared ['source','synthetic']
```

Measured before the change, full demo-api suite, `--crdb=reuse`, from the JUnit XML:
`tests=524 passed=453 failures=6 errors=64 skipped=1`, with
`test_seed_covers_every_console_resource::…[silence]` among the six.

## 2 · Which side is authoritative, and why it is not the seed

The two undeclared keys are the *smaller* half of the defect. The larger half decides the
direction on its own: `contracts/silence.schema.json` `$defs.boundary_leaf` is an **object**
requiring `index`, `leaf_hash_hex` (sha256 hex), `score` and `path_hex`; the seed wrote an
**array**. A contract that is merely too narrow can be argued about. A seed that writes `[]`
where a Merkle inclusion path belongs has not encoded a proof at all — there is nothing in it
for the contract to be too narrow *about*.

So: **the contract and the console are authoritative; this row was wrong**, and the row moved.

Three repairs were available and all three are refused, for reasons that outlive this row:

* **Widening `silence.schema.json`** — the console would then render an exhibit that proves
  nothing, over a schema that says it does.
* **Adding `source` / `synthetic` to the schema** — `additionalProperties: false` is the
  sentence being deleted. The demo already marks synthetic-ness where it belongs
  (`evidence_summary: 'SYNTHETIC — …'`, the envelope's staged flag); a hashed evidentiary
  object is not that place.
* **Teaching `read_silence` to ignore or strip undeclared keys** — this is precisely the
  defect `test_no_read_silently_drops_a_provenance_claim` exists to catch.
  `reads.py::Unrepresentable` is correct, and is not weakened, narrowed or caught.

`reads.py`, `silence.schema.json` and `test_seed_covers_every_console_resource.py` are untouched
by W1 — `silence.schema.json` carries no diff against `e944407` at all — and no assertion,
ratchet or contract was weakened, narrowed or caught anywhere.

## 3 · Every field is derived. Here is the derivation, and the rule that forces it

The receipt's own scalars — `theta = 0.35`, `s = 1`, `n = 1` — are the **givens**. They did not
move. Everything below is read off them by the product's own rules.

| field | value | the rule that produces it |
|---|---|---|
| `s`, `n` | 1, 1 | already seeded; `CHECK boundary_sane (0 ≤ s ≤ n)` holds. `recall_run` declares `n_candidates 1 = n_blocking 1 + 0 + 0 + 0` (MI17): the one candidate was raised, nothing was silenced. |
| `leaf_s.score` | `0.35` | `trappoint_recall.per.receipt.derive_theta_q`: theta **is** the minimum score over the raised leaves. One raised leaf ⇒ that minimum is its score ⇒ score = theta. Read off theta, not chosen. |
| `score_q` | `350000` | `Q(0.35)` — `spec/wire/candidate-commitment.md` §2, round-half-up over the exact binary64. Verified with `quantise_micro(0.35)`. |
| `tau_applied` | `0` | `blocking_check.origin = 'blame_ancestry'` is channel A. `trappoint_recall.run.contract.Candidate` **refuses** a deterministic-origin candidate with `tau_applied ≠ 0.0`: no threshold was consulted, so none may be claimed. |
| `outcome` | `blocking` | `recall_run.n_blocking = 1`, and §3's `blocking_check` is the row it produced. |
| `event_id` | `dec0de00-0005-…-0001` | `blocking_check.precursor_event_id` — DEMO-INC-0001, `demo_world.sql` §5 *THE PRECURSOR*, the event the recall actually found. Interpolated **from the row**, not typed into the preimage. |
| `ord` / `index` | 1 / 0 | `src/verify/silenceroot.ts`, normative: receipt positions are 1-based, Merkle indices 0-based, so `leaf_s` is index `s − 1 = 0`. The verifier checks that relation rather than deriving it. |
| `path_hex` | `[]` | RFC 6962 §2.1.1 — a one-leaf tree has no sibling. `audit_path(0, [h]) == ()`. |
| `leaf_s_plus_1` | JSON `null` | `s = n`: every candidate was surfaced, so there is no first-excluded leaf. `silence.schema.json` models this as `oneOf [boundary_leaf, null]`; `silenceroot.ts` files a finding if `s = n` and a leaf is nevertheless supplied. Written as `null`, never omitted — absence is information. |

## 4 · The question the brief insisted on: does it VERIFY, or only typecheck?

**It verifies.** `candidate_root` is, by definition, `MTH(leaf_hashes)` —
`build_receipt` sets `candidate_root=root` from the leaves — and `merkle_root` of a one-leaf
tree *is* that leaf's hash. So:

```
leaf   = sha256(0x00 || {"event_id":"dec0de00-0005-4000-8000-000000000001","ord":1,
                         "outcome":"blocking","score_q":350000,"tau_applied":0})
       = f23c05695dd3e22bbf58905c877632d6420fac41f817a43842ccc634b40c26ab
candidate_root = MTH([leaf]) = the same 32 bytes
verify_audit_path(leaf, index=0, tree_size=1, path=(), root=candidate_root) → True
```

and the negative control that makes the claim falsifiable:

```
old candidate_root = digest('mainline-demo/recall/candidate-root','sha256')
                   = b63633c15972d12f74725a0cf7e5eba254763638bd9239a2dceca47572a1900c
verify_audit_path(leaf, 0, 1, (), old)                                   → False
```

The old root is the root of no tree. Under it the console's verifier
(`verifyBoundary` → `verifyInclusion`) would have painted a **red seal on a receipt that
parsed** — the worst of the available outcomes, because it looks like diligence.

All six of `verifyBoundary`'s assertions now hold: `0 ≤ s ≤ n`; adjacency (vacuous at `s = n`,
and the `leaf_s_plus_1 !== null` finding is not triggered); `leaf_s.index === s − 1`;
`score(leaf_s) ≥ theta` (`0.35 ≥ 0.35`, compared as decimal strings, never as doubles);
sortedness (vacuous); and inclusion against `candidate_root`.

### Which side moved, and why that side was the derived one

**`candidate_root` moved.** It is the *output* of the commitment, not an input: the leaves are
the input and `MTH` is the function. `digest('mainline-demo/recall/candidate-root','sha256')`
was a name-shaped placeholder occupying an output slot. Moving it to the value its own
definition produces is not moving an authoritative value to match a derived one — it is
computing the derived value at last. Nothing else in the repository reads that constant:
`grep` for `candidate-root` finds only `scripts/proof/gate_refusal.py:1077`, which seeds its
own receipt into its own database and is untouched.

## 5 · The database computes the leaf; the seed does not carry it as hex

Following the convention every other digest in these seed files uses, the value is produced by
`digest(...)` at apply time rather than typed in:

```sql
WITH boundary AS (
  SELECT digest('\x00'::BYTES
                || ('{"event_id":"' || e.event_id::STRING || '","ord":1,"outcome":"blocking",'
                    || '"score_q":350000,"tau_applied":0}')::BYTES, 'sha256') AS leaf_hash
    FROM mainline.event AS e
   WHERE e.event_id = 'dec0de00-0005-4000-8000-000000000001'
)
```

Two properties this buys:

* **`event_id` is interpolated from the row.** A hashed preimage carrying a hand-typed copy of
  an identifier can silently stop describing the event it claims to commit to. This is the same
  reasoning that makes `demo_world.sql` derive the demo credentials from their names.
* **The failure is loud.** If `dec0de00-0005-…` ever ceases to exist, the CTE is empty, the
  INSERT writes nothing, and §4's `exposure_receipt.silence_receipt_id` FOREIGN KEY
  (migration 0199) fails the seed with `23503`. It cannot seed a demo with no receipt.

Cross-checked three ways: CockroachDB's `digest` agrees byte-for-byte with
`trappoint_recall.per.leaf.leaf_hash` (`f23c0569…26ab` from both), the preimage is 113 bytes in
both, and its text matches `spec/wire/candidate-commitment.md` §3.2's emitted member order
`{"event_id":…,"ord":…,"outcome":…,"score_q":…,"tau_applied":…}`.

## 6 · Re-appliability — and the row that is already wrong in a deployed database

`ON CONFLICT DO NOTHING` would have been the smaller edit and it is the wrong one, for a reason
that has nothing to do with this suite. **Every database seeded before 2026-08-14 — including
the deployed `mainline_demo` — already holds this row with the old `boundary_proof`.** A seed
statement that declines to touch an existing row leaves the repair unreachable: the suite goes
green against freshly built fixture databases while the console link a judge clicks stays
broken. That is this repository's signature failure mode, and it is the one the credential
incident was made of.

So the statement is `INSERT … SELECT … ON CONFLICT (silence_receipt_id) DO UPDATE SET
candidate_root, boundary_proof … WHERE silence_receipt.candidate_root != excluded.candidate_root`.
It is the only statement in the file that can change a row it did not write; the `WHERE` makes
it a no-op the instant the row is already right, and it rewrites those two columns and nothing
else.

Measured on the scratch database `w_w1`, with the statement cut out of the seed file rather than
re-typed, holding schema, code and permit fixed:

| | rows | `candidate_root` | `read_silence` |
|---|---|---|---|
| **state A** — the row as the old seed wrote it | 1 | `b63633c1…` | `Unrepresentable` (409) |
| apply #1 | `rowcount = 1` | | |
| **state B** — after one apply | 1 | `f23c0569…` | renders |
| apply #2 | `rowcount = 0` | | |
| apply #3 | `rowcount = 0` | 1 row, unchanged | renders |

and, separately, on a database **rebuilt from zero** (`cloud_chain.py --recreate`, 271/271
applied) with both seed files applied **twice** through `scripts/deploy/seed_demo.py` — the
deployment's own applier, one batch per file: both runs exit 0, `VERDICT SEEDED AND REFUSABLE`,
one `silence_receipt` row, `INCLUSION VERIFIES: True`.

`mainline_meas.silence_receipt` carries no `BEFORE` trigger today (grep over
`db/migrations/*.sql`; the `0128*` refuse-mutation family covers `permit_event`, `cr_event`,
`blocking_check`, `merge_record`, `exposure_receipt`, `exposure_line`, `override_ledger`,
`person`, `signing_credential`, `clause_version` and `clause_blame_closure`, and not this
table). If one is ever added, this statement is where it will be felt, and the `WHERE` above is
what keeps the second apply from writing at all.

## 7 · What this receipt still does NOT establish, stated rather than implied

* **`mainline_meas.recall_candidate` has no rows.** The demo's `recall_run` declares
  `n_candidates = 1` and this receipt commits to that one candidate, but the candidate *row*
  is not seeded by either file, so nobody can rebuild the leaf from the candidate table — only
  from this receipt and the event. Every member of the leaf is derived from a row that does
  exist (§3), so nothing here is invented; but the reconstruction path a verifier would prefer
  is absent. **Reported, not repaired:** seeding `recall_candidate` touches `0139
  trg_candidate_project` and `0137 trg_bonded_sev5`, is outside §3.2's ruling, and belongs to
  whoever owns the recall seed as a whole.
* **PER's bound is unchanged and still applies.** This receipt proves exhaustion of the
  retrieval that ran, not of the corpus. `bound.statement` remains the one value in the silence
  payload that no column produces, and `read_silence` still flags the envelope `staged` and
  says so.
* **A one-leaf tree is a small proof.** It is a *correct* one: the boundary sits at the end of
  the multiset, `boundaryAtEnd` is true, and the console renders that state rather than
  claiming a bracket it does not have.

## 8 · Measurements

Full demo-api suite, `--crdb=reuse`, read from `--junitxml` and from nowhere else:

| | tests | passed | failed | errors | skipped | wall |
|---|---:|---:|---:|---:|---:|---:|
| **before** (this seed unmodified) | 524 | 453 | 6 | 64 | 1 | 51.5 s |
| **after** (final bytes) | 528 | 454 | **0** | 63 | 11 | 105.9 s |

**Regression set, node id by node id across the two XMLs: EMPTY.**

`test_seed_covers_every_console_resource::…[silence]` moves **FAILED → PASSED**. The remaining
**63 errors are `test_reads.py`'s `payloads` fixture and are expected to remain until W2 lands**
(plan §1: the fixture builds all twelve reads before any test runs, so W1 and W2 clear them only
together). Their cause has moved on, which is the measurement that matters here: the fixture now
stops at `KeyError: 'commit_v2'` — blocker 1, W2's — and `boundary_proof` no longer appears in
any of them. A run reporting "still 63 errors" has measured correctly.

The other five failures that cleared in the same window are **not W1's**: four
`test_response_contract` (W4) and `test_an_undeclared_query_parameter_is_refused_rather_than_ignored`
(W3's ledger seeding). The ten extra skips are all `test_credentials`, skipped for a named
environmental reason — `81 of 271 migrations did not apply into w1_credentials_3b0aafc625f2` —
which is the shared node under six concurrent workers, not this change.

**Caveat on the after-run, stated because it is a measurement and not an excuse.** This wave's
six workers share one working tree and one single-node CockroachDB. Between the before-run and
the after-run, `demo_world.sql`, `db.py`, `test_reads.py`, `test_response_contract.py` and
`test_transitions.py` all changed under W1, and the shared node repeatedly failed to apply part
of the migration chain into a fixture database while several workers built theirs at once
(`13 of 271`, `28 of 271`, `81 of 271`; first failure `relation "mainline.permit" does not
exist`). Two intermediate runs therefore showed six-node "regression sets" in
`test_transitions` and `test_gate_run` which **re-ran green immediately, unchanged tree, 6/6 and
53/53** — those tests drive `w_w4_api_transitions`, a database the demo seed does not touch and
which every concurrent worker's suite run shares, so their byte-identity assertions flap under
concurrency. The final run's regression set is empty, and §6's A/B — which holds schema, code
and permit fixed and moves only this row — is the evidence that does not depend on the tree
holding still.

## 9 · Consequences for files W1 does not own, reported rather than edited

`tests/ci/test_demo_seed_is_frozen.py` freezes `sha256(demo_permit.sql)` at
`198d44ef…dcc6` — the value on disk before this change. That test is **not** in the demo-api
suite (it lives in `tests/ci/`), and W1 does not own it, so it is left alone. Its own docstring
states the condition for a re-baseline, and this change meets it: *"the commit that changes the
hash says what changed in the seed and why, and a reviewer reads that sentence."* The sentence
is this document. **The re-baseline must land in the same commit as this seed change.** The new
hash is reported in W1's structured output rather than written here, so that no second copy of
it can drift from the file.

Three more places now describe a defect that no longer exists. All three are left exactly as
they are, because W1 owns none of them and a worker editing prose outside its lane is how a
wave loses track of what it changed:

* `verticals/mainline/apps/demo-api/tests/test_seed_covers_every_console_resource.py:66-75` —
  the docstring paragraph *"A third failure mode turned up the first time this file was run…
  `silence` answers neither a payload nor a `NotFound` but `Unrepresentable`"*. The paragraph's
  ruling ("the assertion was left exactly where it was rather than narrowed to `NotFound` to
  obtain a green") was **correct and is vindicated**: the assertion never moved, the seed did.
* `docs/diagnosis/demo-suite-falsification.md` §5 (and its lines 41, 350, 369) — the same
  finding, recorded as a standing defect.
* `scripts/deploy/seed_demo.py:30-34` — *"Both seed files use … `ON CONFLICT DO NOTHING`."*
  The property that docstring actually asserts still holds and is measured in §6 (a second run
  inserts nothing, raises nothing, identical row counts); the blanket description of the
  mechanism no longer does.
