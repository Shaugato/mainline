<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Suite-green plan — the demo-api suite against a real cluster

**Lead:** suite-green. **Date:** 2026-08-14. **HEAD:** `e944407` (working tree dirty — see §0.3).
**Scope:** blockers 1, 2, 5, 6, 7 plus randomised-order proof; blocker 3 folded into W6.

---

## 0 · The baseline I measured myself

Command, run once, numbers read from the JUnit XML root element and from nowhere else:

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
    --crdb=reuse -q -p no:cacheprovider --junit-xml=<report>.xml
```

| tests | passed | failed | skipped | errors | wall |
|---:|---:|---:|---:|---:|---:|
| **524** | **454** | **6** | **1** | **63** | **50.873 s** |

Report: `C:/Users/shaug/AppData/Local/Temp/claude/D--CoackroachDBxAWS/b1150179-8ec5-4ec7-bdfb-3da356eb4402/scratchpad/baseline/before.xml`

### 0.1 Two corrections to the brief, both measured, neither cosmetic

* **The brief says 453 passed / 7 failed. I measured 454 / 6.** The one-test difference is
  the documented non-deterministic flapper in `test_transitions.py`
  (`qa/cluster-known-red.json` → `unstable`, 3 node ids, each observed failing in 1 of 3
  identical runs). I am not treating either number as authoritative on its own; §4 W6 is
  what turns "not observed" into a measurement.
* **The brief warns a full `--crdb=reuse` run takes 25 minutes. Mine took 51 seconds.**
  The difference is the adopted database (`w3_demo_api_885e1182f4e6` was already built, so
  271 migrations were not re-applied) — *and*, I suspect, the connect-path defect in §3.7,
  which charges 10 s per cold connection to any DSN spelled `localhost`. Workers must still
  take numbers from `--junitxml`, never from a terminal scroll; but nobody should kill a run
  believing 51 s means it did not run. Check `tests=` in the XML.

### 0.2 The six failures decompose into exactly four causes

| failure | blocker | owner |
|---|---|---|
| `test_reads::test_an_undeclared_query_parameter_is_refused_rather_than_ignored` | 6 | W3 (seed) → W2 (assert) |
| `test_response_contract` × 4 | 2 | W4 |
| `test_seed_covers_every_console_resource[silence]` | 5 | W1 |

The 63 errors are one cause (blocker 1) **plus a second one hiding behind it** — see §1.

### 0.3 The tree is dirty and the re-verification's first check applies to it

`git status --porcelain` shows **46 modified** and **34 untracked** paths at `e944407`,
including `verticals/mainline/db/seeds/demo/demo_world.sql`,
`verticals/mainline/apps/demo-api/tests/*` and `src/mainline_demo_api/*`. The fifth
re-verification's first check — a `git diff` over every seed / fixture / ceiling / threshold
asking whether an authoritative side was moved to match a derived one — therefore runs over
**uncommitted work**, not over a clean checkout. Every worker below must leave its own diff
readable as an answer to that question, and must say in its report which side it moved and
why that side was the derived one.

---

## 1 · THE FINDING THAT REORDERS THE WAVE: blockers 1 and 5 are serially coupled

The brief treats blocker 1 (63 errors, `KeyError: 'commit_v2'`) and blocker 5 (one failure,
`silence_receipt.boundary_proof`) as separate items. **They are the same 63 errors.**

I measured this rather than reasoning about it. With `test_reads.py:95` changed from
`seed["commit_v2"]` to `seed["commit_id"]` and nothing else touched:

```
1 failed, 11 passed, 63 errors in 8.91s
```

The errors did not move — only their cause did. The `payloads` fixture is session-scoped and
builds **all twelve** reads before any test runs; `clause_version` is the sixth and `silence`
the ninth. Fixing the sixth just lets the fixture walk into the ninth:

```
mainline_demo_api.reads.Unrepresentable: mainline_meas.silence_receipt
dec0de00-000a-4000-8000-000000000001 carries a boundary_proof silence.schema.json cannot
express: boundary_proof carries ['leaf_s','leaf_s_plus_1','source','synthetic'] where the
contract declares ['leaf_s','leaf_s_plus_1']; undeclared ['source','synthetic'].
```

**Consequence for the wave: neither W1 nor W2 alone can show the 63 errors clearing. Only
both together can.** A worker who lands one and reports "still 63 errors, no progress" has
measured correctly and must not conclude their change was wrong. W2's `done_when` is written
around this.

`qa/cluster-known-red.json`'s `reads-payloads-fixture-refuses-to-invent-a-subject` group
still names `cr_id` as the cause. It is stale twice over — `cr_id` was seeded, then
`commit_v2` became the cause, and now `boundary_proof` is the second one. Updating it is
**not** in this wave's scope (it belongs to the cluster lane, and the group is expected to be
*deleted* rather than edited); W2 reports the staleness, and does not touch the file.

---

## 2 · Where the demo seed and the test suite disagree, and the one question underneath

Three of my five blockers are the same defect wearing three hats. `test_reads.py` describes a
world **richer than `demo_world.sql` + `demo_permit.sql` build**, and each place the two
disagree is a place somebody will be tempted to move whichever side is easier.

Measured against the seeded database `w3_demo_api_885e1182f4e6` (built by the deployment's own
applier from the two seed files):

| what the suite assumes | what the seed actually carries |
|---|---|
| two clause versions, the second `strengthen` with anchor `WITNESS` and witness `R6_VERIFICATION` | `SELECT … FROM mainline.clause_version` → **exactly one row**, `gen = 1`, `control_delta = 'introduce'`, `anchor_set = ['LOTO','ZERO_ENERGY']` |
| ledger leaves at `seq` 0 and 1, inclusion proofs, a consistency proof between two checkpoints | `mainline.ledger_leaf` → **0 rows**; `mainline.ledger_node` → **0 rows**; `mainline.ledger_checkpoint` → **1 row, `tree_size = 1`**; `mainline.ledger_intake` → 1 row |
| a silence receipt renderable under `silence.schema.json` | `boundary_proof` = `{"synthetic":true,"leaf_s":[],"leaf_s_plus_1":[],"source":"…demo_permit.sql"}` |

**The question underneath all three: when the seed and the suite disagree, which is
authoritative?** Neither, by itself. The tiebreaker this repository already uses is written
down in `tests/test_seed_covers_every_console_resource.py`, and I adopt it unchanged:

> **The console is the authority for which resources exist.** It is the artefact a judge
> drives… Seed it, or delete it from `resources.ts`.

I extend it one notch, because that file only settles *existence* and the three rows above are
about *content*: **the console and the committed JSON Schemas are the authority for what the
demo must CARRY; the seed and the tests are both checked against them, and either may lose.**
That is why my three rulings below do not all go the same way. A rule that always moved the
seed, or always moved the test, would not be a rule — it would be a preference.

---

## 3 · Rulings. These are decided. No worker re-opens one; a worker who finds
## evidence against one STOPS and reports rather than proceeding either way.

### 3.1 — Blocker 1: `commit_v2`. **The demo has ONE clause version. Assert it.**

`test_reads.py:95` asks for `seed["commit_v2"]`. The fixture has never produced it.
`git log -S commit_v2` puts the name in at `5ddaa3a`, inside the *old* conftest that built a
parallel world with `_sha("commit","clause-v1")` and `_sha("commit","clause-v2")`. The rewrite
that made the fixture read the deployed seed deleted that world; `test_reads.py` was not
updated. **`commit_v2` is a survivor of the parallel world, not a product decision.**

I ruled *against* seeding a second version, on four pieces of evidence outside both the test
and the seed:

1. **No console path reaches a v2.** `features/gate/useGateData.ts:193` addresses the clause
   version at `subjectCheck?.commit_id` — the commit the *blocking check* cites, which is
   `clause-v1`. `ClauseDiffScreen.tsx`'s `DEMO_COMMIT` fallback is
   `5f916282…e576`, a placeholder that is neither seeded commit. Nothing in the console
   constructs `clause-v2`. Under §2's tiebreaker that ends it: the console does not tell a
   judge a second version exists.
2. **The console renders a single-version clause deliberately.** `features/diff/engine/build.ts`
   `comparabilityOf()` returns `{kind: 'origin_version'}` when a version names no parent. That
   is a first-class modelled state with its own rendering, not a degraded one.
3. **Seeding a v2 would contradict two rows the seed already carries.**
   `mainline.clause.head_commit` is `clause-v1`, and `cr_clause` relation `'edits'` names
   `(clause_uuid, clause-v1)` — the demo's narrative is *"a change request PROPOSES to edit
   v1"*. A v2 that already exists makes the open change request propose an edit that has
   already happened.
4. **§3 of `demo_world.sql` is not missing a commit.** It says "Two commits and the edge
   between them" and seeds `root` → `clause-v1`. The DAG is complete as designed.

**Therefore:** `test_reads.py:95` takes `seed["commit_id"]`, and
`test_the_clause_version_reports_its_witnesses_as_a_positive_claim` is rewritten to assert the
world the seed actually carries.

**This is a case of a TEST being moved toward a SEED, which is the direction the no-shortcut
rule exists to police, so the burden of proof is higher and it is discharged above by evidence
from the console — a third artefact that is neither of the two in dispute.** The rewritten
test must keep making the *positive* claim its name promises: `[]` and `null` are different
sentences, and an origin version's `parent` being `None` must be asserted as a fact about an
origin version, not deleted because it is inconvenient. If W2 cannot make the rewritten test
say something falsifiable, W2 reports that instead of writing a weaker test.

### 3.2 — Blocker 5: `boundary_proof`. **The contract is authoritative. The SEED is wrong.**

`silence.schema.json` `$defs.boundary_leaf` requires an **object** with
`index`, `leaf_hash_hex`, `score`, `path_hex`. The seed writes `"leaf_s": []` — an **array**.
So the seeded proof is wrong on a point where the contract is unambiguous, quite apart from the
two undeclared keys. That settles the direction: this is not a contract that is too narrow, it
is a seed that does not encode a Merkle inclusion path at all.

Widening the schema, or teaching `read_silence` to ignore undeclared keys, are both refused:
the first lets the console render an exhibit that proves nothing, and the second is the exact
"silently drops a provenance claim" defect `test_no_read_silently_drops_a_provenance_claim`
exists to catch. **`reads.py::Unrepresentable` is correct and must not be weakened, narrowed,
or caught.**

`source` / `synthetic` are the repository's convention for marking synthetic data, and the
demo marks synthetic-ness elsewhere (`message: 'SYNTHETIC — …'`, `envelope.kind`). The
`boundary_proof` object is not the place for it, and `additionalProperties: false` says so.

### 3.3 — Blocker 6: the ledger. **The SEED is wrong, and worse than the brief says.**

The brief describes this as "the ledger range read returns no leaves". It is sharper than
that. I measured, against the seeded database:

* `mainline.ledger_checkpoint` → **1 row, `tree_size = 1`**
* `mainline.ledger_leaf` → **0 rows**
* `mainline.ledger_node` → **0 rows**

**The demo's transparency log publishes a checkpoint claiming a tree of size 1 over zero
leaves.** That is not a thin seed; it is a signed claim with nothing behind it, in the one
surface whose entire purpose is that claims have something behind them. It is also why
`test_every_inclusion_proof_verifies_against_the_checkpoint_it_names` and
`test_the_consistency_proof_between_the_two_checkpoints_is_present` — both currently hidden
inside the 63 errors — will fail the moment the fixture builds.

The suite is right and the seed is wrong. **Seed the ledger.** Two constraints make this
honest rather than fabricated:

* **The leaves must be appended through `mainline.fn_ledger_cas_append`** (`0073_ledger_leaf.sql`),
  the product's own gap-free compare-and-swap appender, so `leaf_hash`, `link_hash` and
  `prev_link_hash` are computed by the database. A seed that writes `digest(...)` literals into
  `ledger_leaf` would be hand-rolling a transparency log, which is the credential-id defect in
  a more embarrassing register.
* **The checkpoints must become true rather than be trusted.** After appending, the
  checkpoint's `tree_size` must equal the number of leaves, and a **second** checkpoint must
  exist so `test_the_consistency_proof_between_the_two_checkpoints_is_present` has two things
  to be consistent between. `read_ledger` already refuses a ledger with no checkpoint
  (`reads.py:1594`) — that refusal stays.

`== [0, 1]` in `test_an_undeclared_query_parameter_is_refused_rather_than_ignored` is
therefore **not** weakened. It becomes true when the seed becomes true.

### 3.4 — Blocker 2, part one: **the DEPLOYED tree is authoritative.**

The question the brief poses: the ceiling governs what this origin COSTS, so is the
authoritative tree what deploys, or what the packer ingests?

**What deploys.** Cost is incurred by bytes leaving the deployed origin. An object that never
reaches the deployed package cannot cost anything, so it cannot be evidence about a cost
control. `console/dist` contains 18 source maps that `build_lambda` strips by default; a
ceiling justified by refusing them would be a ceiling justified by refusing objects that are
not there — the identical error the module's own comment says produced the previous wrong
value.

I verified the deployed tree myself, from the central directory of
`out/lambda/mainline-demo-api-arm64.zip` (built 2026-08-13 15:54, present on disk):

```
web/ entries        114 files   1,274,342 B
  identity objects   57 files     985,030 B
  .gz siblings       57 files     289,312 B
  source maps         0 files           0 B
largest identity                 433,396 B   web/assets/index-BjAGxrVJ.js
second-largest identity           51,266 B   web/assets/surface-Csi7pmRe.js
largest .gz sibling              124,127 B   web/assets/index-BjAGxrVJ.js.gz
identity objects over the 139,264 B ceiling:  exactly one — index-BjAGxrVJ.js
.gz siblings over the ceiling:                none
```

**Every figure in `static_site.py`'s comment block is true against the built zip.** So:

* **`DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024` is CORRECT and does not move.** It satisfies I3
  on the authoritative tree: `largest_served_wire_bytes = 124,127`;
  `1.10 × 124,127 = 136,540`; next 8 KiB multiple = **139,264**;
  `139,264 / 124,127 = 1.122 < 1.20`. The number is a consequence of the rule, not an input.
* **`test_response_contract.py`'s declarations are what is wrong**, because they were measured
  against the packer's input tree. Under the ruling they become:
  `_LARGEST_SERVED_OBJECT` = the largest object the origin actually serves = the largest `.gz`
  sibling at **124,127 B**; `_LARGEST_WEB_OBJECT` = the largest thing the deployed tree holds
  and the ceiling refuses = **`assets/index-BjAGxrVJ.js` at 433,396 B**;
  `_REFUSED_BY_THE_CEILING` = **`("assets/index-BjAGxrVJ.js",)`** on the identity path.
  The derived constants follow: `headroom = 139,264 − 124,127 = 15,137`;
  `cut = 433,396 / 124,127 = 3.4917`.

**This is emphatically not "pasting the measured list into the expectation".** The input tree's
measured list is `['index-BjAGxrVJ.js', 3 maps, …]`; the ruling's list is `index.js` **alone**,
and the maps are absent *by construction* because the packer strips them. The two lists differ.
W4 must **derive** each number from the zip and the I3 formula and show the arithmetic — a
number that merely happens to equal what a run printed is not evidence.

Two hazards W4 must handle rather than route around:

* `.gz` siblings have no URL of their own (interface I1: a direct request for a path ending
  `.gz` is a **404**). Enumerating all 114 `web/` entries and collecting every non-200 would
  file 57 404s as "refusals". The enumeration must cover **identity objects**, and the `.gz`
  404 must be asserted as its own property, not swept into the refusal set.
* The test must read the **built zip**, which is a build output. A missing zip must fail loudly
  or skip under a ratchet that cannot pass vacuously — `_require_built_tree()` already exists
  for this and must not be softened into a silent skip.

### 3.5 — Blocker 2, part two: **the base64 test encodes a SUPERSEDED metric. I2 wins.**

`test_base64_inflation_is_measured_and_not_assumed` asserts a 3,300 B non-UTF-8 file under a
4,096 ceiling answers **413**, because base64 inflates it to 4,400. It now gets **200**.

That is not drift. It is a ratified interface change, and I checked that it was ratified
**outside the module that changed** before allowing the test to move —
`docs/leads/cost-finish-plan.md:242`:

> **I2 — the ceiling is measured on WIRE bytes.** The billed quantity is what leaves Lambda
> after it decodes base64, not the base64 string. … **a ceiling applied to the encoded string
> would over-refuse by exactly that.** This is the subtlest hazard in the wave.

I2 is right on the merits for a *cost* control: AWS bills data transfer out on the decoded
bytes the client receives; the base64 envelope is transport overhead between the Lambda and
the Function URL service. So the test asserts the wrong metric and the code asserts the right
one.

**But the test's NAME still names a real obligation** — the inflation must be *measured*, not
assumed — and it must not be reduced to `assert 200`. W4 rewrites it so it still refuses a
real failure mode: that the ceiling is applied to the **decoded** length, that
`_wire_bytes` computes that length arithmetically from the base64 string without decoding it,
and that the **encoded** payload stays under Lambda's 6 MB response-payload quota, which *is*
measured on the encoded string and which nothing currently asserts. If W4 cannot make it
falsifiable, W4 reports that rather than shipping a tautology.

**Had I not found I2 ratified outside `static_site.py`, the ruling would have gone the other
way** — a module that changes a metric and documents the change in its own docstring is a
module marking its own homework, and the test would have been authoritative.

### 3.6 — Blocker 3: the lane's claim about itself is false. W6 makes it true or deletes it.

`scripts/ci/cluster_lane_report.py` has zero controls (`tests/ci/` holds one unrelated file,
`test_demo_seed_is_frozen.py`) while `cluster-tests.yml` asserts *"Both properties are
exercised by controls."* A report nobody can falsify is decoration. W6 writes the controls; if
a property turns out not to be exercisable, **the sentence in the workflow comes out** — the
claim is not allowed to stand unsupported either way.

### 3.7 — Blocker 7: `/v1/health` at 10 s. **TWO defects, both in `db.py`, neither in `health.py`.**

The brief says `/v1/health` takes 10.1 s and asks why. I measured, and the answer is not what
the suite's timings suggest.

**First, the suite's 10.1 s is not the healthy path.** The 10.05 s node in my baseline XML is
`test_envelope::test_health_is_503_when_the_database_does_not_answer`. The healthy path in the
suite (`test_reads::test_health_reads_the_deploy_chain_marker_when_the_database_has_one`) is
**1.96 s**.

**Second — and this is the finding — the healthy path takes 10 s too, whenever the DSN says
`localhost`.** Timing `health.health()` directly:

```
HEALTHY      200  10.038 s   (body.seconds = 10.0383)
HEALTHY-warm 200  10.012 s
UNREACHABLE  503  10.042 s
raw psycopg.connect to 127.0.0.1:1, connect_timeout=2   → 2.005 s
```

Decomposing it: `db.connection()` costs **10.102 s**; `HEALTH_STATEMENT` costs **0.003 s**.
The whole ten seconds is the connect, and none of it is the query, the retry loop
(`READ_RETRY_ATTEMPTS` retries `40001` only — everything else propagates on first occurrence),
or anything in `health.py`.

The two mechanisms, isolated:

**(a) IPv6-first name resolution, paid in full.**
```
getaddrinfo('localhost', 26257) → [AF_INET6 ('::1',26257), AF_INET ('127.0.0.1',26257)]
psycopg.connect  'localhost'  , no connect_timeout  → 130.101 s
psycopg.connect  '127.0.0.1'  , no connect_timeout  →   0.003 s
```
The node listens on IPv4 only. libpq applies `connect_timeout` **per address**, so every cold
connect burns the entire timeout against a dead `::1` and then succeeds instantly on IPv4.
`CONNECT_TIMEOUT_SECONDS = 10` is exactly the 10.04 s observed. (The 130.1 s figure is the same
mechanism with no timeout at all — and it is the *same number* the repository-root `conftest.py`
already recorded on 2026-08-10 and attributed to a black-holed address. That attribution looks
incomplete.)

**(b) `_open` silently overrides the caller's `connect_timeout`.**
```python
def _open(dsn: str) -> psycopg.Connection[Any]:
    return psycopg.connect(dsn, autocommit=True,
                           connect_timeout=CONNECT_TIMEOUT_SECONDS, ...)
```
A keyword argument outranks the DSN's query string. `test_health_is_503_when_the_database_does_not_answer`
asks for `connect_timeout=2` in its DSN and gets 10 — which is the whole of its 10.05 s, and
which means **no caller can currently choose a shorter connect budget than the module's**.

**Ruling.** These are real defects and neither is fixed by moving a ceiling. Specifically
**forbidden** as a fix: rewriting the test's DSN to `127.0.0.1` and declaring the timing
repaired. That makes the suite green while leaving the deployed Lambda paying 10 s per cold
start if its CockroachDB Cloud hostname resolves AAAA-first — the exact class of green that
this repository has been burned by. W5 fixes the connect path itself, proves (a) and (b)
separately with falsifiable controls, and **must determine and report whether the deployed
DSN's hostname has an AAAA record** (a read-only DNS lookup; no `terraform apply`, no
credential printed). If it does, this is a production latency and cost finding, not a test
finding, and W5 says so in writing.

`timeout` stays a reliability bound and does not move (already-true list). LATENCY.md's
measured 14 s stands unless W5's measurement supersedes it *with a measurement*.

---

## 4 · The six workers. Paths are disjoint and literally enumerated.

Every brief carries the same three obligations, and they are not boilerplate:

* **Report full-suite `--crdb=reuse` numbers BEFORE and AFTER, read from `--junitxml`.**
  Not from a terminal scroll. Compute the regression set as a node-id-by-node-id difference
  of the two XMLs, and report it even when empty.
* **NEVER move an authoritative value to match a derived one.** If you believe a fixture,
  seed, ceiling, threshold or expected value is wrong, say so with evidence and leave it
  alone. Changing one to obtain a green converts a real defect into a permanent invisible one.
* **A ruling in §3 is decided. If you find evidence AGAINST one, STOP and report it.** Do not
  proceed in either direction on your own authority.

### W1 — the silence receipt's boundary proof
**Owns:** `verticals/mainline/db/seeds/demo/demo_permit.sql`,
`docs/decisions/demo-silence-boundary-proof.md` (new).
**Blocker 5.** Depends on nothing. **Unblocks W2.**

### W2 — `test_reads.py`, the whole file
**Owns:** `verticals/mainline/apps/demo-api/tests/test_reads.py`,
`docs/decisions/demo-clause-version-singleton.md` (new).
**Blockers 1 and 6 (assertion side).** Depends on W1 and W3.

### W3 — the ledger the demo publishes
**Owns:** `verticals/mainline/db/seeds/demo/demo_world.sql`,
`docs/decisions/demo-ledger-seeding.md` (new).
**Blocker 6 (seed side).** Depends on nothing. **Unblocks W2.**

### W4 — the response ceiling and the tree it governs
**Owns:** `verticals/mainline/apps/demo-api/tests/test_response_contract.py`,
`verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py`,
`docs/decisions/response-ceiling-authoritative-tree.md` (new).
**Blocker 2.** Depends on nothing.

### W5 — the connect path
**Owns:** `verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py`,
`verticals/mainline/apps/demo-api/tests/test_envelope.py`,
`docs/diagnosis/health-connect-path.md` (new).
**Blocker 7.** Depends on nothing.

### W6 — randomised order, and the lane's own falsifiability
**Owns:** `pyproject.toml`, `tests/ci/test_cluster_lane_report.py` (new),
`scripts/ci/cluster_lane_report.py`, `docs/ci/demo-suite-random-order.md` (new),
`docs/ci/cluster-lane-report-controls.md` (new).
**Blockers 4 and 3.** Depends on nothing.

**Files nobody in this wave owns, and nobody edits:** `qa/cluster-known-red.json` (stale; W2
*reports* it), `docs/HONESTY.md`, `docs/CI-STATE.md`, any ratchet,
`scripts/deploy/kill_switch.{sh,ps1}`, `infra/**`, `docs/deploy/LATENCY.md`.

---

## 5 · Sequencing

```
W1 ──┐
     ├──► W2  (the 63 errors clear only when W1 AND W3 have landed)
W3 ──┘
W4, W5, W6 — independent, start immediately
```

W4, W5 and W6 touch no file W1/W2/W3 touch and may run concurrently with them.

## 6 · What "green" means, and what it does not

Green is `0 failed, 0 errors` on a full `--crdb=reuse` run whose XML shows `tests ≥ 524` and
`skipped ≤ 1` — a floor, so that a suite which collects less cannot pass by collecting less.
It is **not** green if it was reached by lowering `min_executed`, raising `max_skipped`,
widening a contract, adding a node id to an inventory, or moving a seed to match a test where
§3 did not rule that the seed was wrong. W6's randomised-order run is what makes the green
mean anything beyond "in this order": until it has run, cross-test contamination is
**not-observed**, which is not the same sentence as **fixed**.
