<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# JUDGE-CAN-SIGN — lead plan

**Lead:** judge-can-sign · **Scope:** blocker 1 (the demo cannot be completed by a judge) and
blocker 6 (nothing here has ever met a multi-node cluster).
**Written:** 2026-08-14 · **HEAD:** `eefae1c`, branch `master`, working tree **clean**
(`git status --porcelain` empty at the time every number below was taken).

---

## 0 · THE RULE THAT OUTRANKS EVERY TASK IN THIS PLAN

A worker was once caught editing `demo_world.sql` to enrol a DERIVED credential id, making the
SEED match the CODE. **When a test and the code disagree, never move whichever side is easier;
ask which side is AUTHORITATIVE.** The ratified tiebreaker: *the console and the committed JSON
schemas are authoritative for what the demo must carry, and the seed and the tests are BOTH
checked against them — either may lose.*

This plan makes a test lose (R2). That is only legitimate because the authority is named, is
outside both the test and the seed, and is quoted below. **A worker who cannot name the authority
outside the file they are about to edit is not allowed to edit it.**

Prohibitions that bind every worker here, restated in each brief and repeated because they have
been broken before: never lower `COLLECTED_FLOOR`, the skip ceiling, or a known-red list to obtain
a green. Never weaken an assertion, `HONESTY.md`, `CI-STATE.md` or a ratchet. `continue-on-error`
and `|| true` are banned. Never print or reconstruct a credential. Never `terraform apply`. Never
answer a collection error with `-k`, `--deselect` or a stubbed import.

---

## 1 · BASELINE — measured by this lead, not inherited

Command, run at `eefae1c` on a clean tree against the local CockroachDB v26.2.5 at
`127.0.0.1:26257`:

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
    --crdb=reuse -q -p no:cacheprovider --junit-xml=<report>
```

Numbers taken from the `--junitxml` `testsuite` attributes, never from the terminal scroll:

| | tests | failures | errors | skipped | time |
|---|---|---|---|---|---|
| **BEFORE (this wave)** | **528** | **1** | **0** | **1** | 53.0 s |

* The **one failure** is `test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements` —
  `AssertionError: assert set() == {'MECHANISM_PRESENT_AND_VERIFIED', 'SCOPE_EXCLUDES_HAZARD'}`.
  That is blocker 1, and it is the only thing standing between this suite and 528/528.
* The **one skip** is `test_gate_run.py::test_payload_validates_against_the_json_schema`
  ("jsonschema is not a workspace dependency"). It is hermetic and has nothing to do with the
  cluster; it is not this wave's.
* This reproduces the brief's claim (528 / 527 passed / 1 failed / 0 errors) exactly. `uv` is
  **not on PATH on this workstation**; the venv interpreter is what runs, and every worker must
  use it. A worker who reports "`uv: command not found`" as a suite result has reported nothing.

**A second, pre-existing red, outside the demo-api suite** — measured because this wave is about
to touch the file it guards:

```
.venv/Scripts/python.exe -m pytest tests/ci/test_demo_seed_is_frozen.py -q --crdb=none
  ->  2 failed, 1 passed
```

`demo_world.sql` hashes `e2aa9706…`, the test records `50535d1d…`; `demo_permit.sql` hashes
`df3470cb…`, the test records `198d44ef…`. **This is red at HEAD, before this wave changes a
byte.** See R5.

---

## 2 · RULINGS

Each ruling names the authority it was ruled from. Nothing below was ruled from "what makes the
test pass."

### R1 — The vocabulary must exist. The seed owes the rows. UPHELD.

**Authority (all outside the seed and outside the test):**
`console/src/data/resources.ts:105` — the disposition resource carries *"the per-check defeater
vocabulary"*. `console/src/app/surfaces.ts:84` — *"a per-check defeater vocabulary with no global
'not applicable'"*. `console/src/a11y/contract.ts:388-391` — step `id: 'defeater'`,
`pointerOnly: false`, sitting inside the claim at line 288 that *the complete path from the
refusal to the signature … is operable with a keyboard alone … with no pointer-only step*.
`console/contracts/disposition.schema.json` — `defeater_options` is in `required` and is a
non-nullable array. `console/src/data/types.generated.ts:727` — declared non-optional.
`db/migrations/0064_defeater_option.sql` — *"generated per check, so no global 'N/A' exists"*.
**Precedent for the tiebreaker being applied this way, in code:**
`test_seed_covers_every_console_resource.py:21` — *"The console is the authority for which
resources exist."*

**RULING.** `mainline.defeater_option` must carry rows for the demo's check
`dec0de00-0007-4000-8000-000000000001`. The failing assertion is upheld **in kind**. Nobody may
weaken it to `== set()`, mark it xfail, or delete it.

**Evidence that this is shipped, not merely local.** The captured bundle from the real deployed
CockroachDB Cloud cluster,
`console/fixtures/bundles/demo-cloud/frames/GET-841e70d4e5f1d244.json`, decodes to
`"staged": false` and `"defeater_options": []` for exactly this check. The judge-facing
deployment is empty too.

### R2 — Which CODES. `MECHANISM_PRESENT_AND_VERIFIED` is authoritative; `SCOPE_EXCLUDES_HAZARD` is not. THE TEST LOSES THIS ONE.

**Measured.** `MECHANISM_PRESENT_AND_VERIFIED` occurs in `transitions.py:1000` (the API's default
for the signer-supplied field), `gate_run.py:141` (hard-coded into beat 4's INSERT),
`scripts/proof/gate_refusal.py:1428`, `scripts/deploy/capture_demo_bundle.py`, the captured Cloud
SQL exhibit `demo-cloud/sql/beat-4-merge-admitted-00000.txt` (outcome **ADMITTED**), and the
captured Cloud API frame `GET-f116fc2724f1b968.json`, whose `signed.defeater_code` is that string.
`SCOPE_EXCLUDES_HAZARD` occurs in **exactly two places in the entire tree**: `test_reads.py:416`,
and `qa/cluster-known-red.json`, which is quoting that test's own failure text. It is in no
schema, no console file, no migration, no runtime module, no capture, no document.

**RULING.** (a) `MECHANISM_PRESENT_AND_VERIFIED` **must** be one of the seeded codes — beat 4
writes it, and a signature naming a code that was never offered is precisely the *"click-through
with a signature on it"* that 0064's rationale exists to forbid. (b) `SCOPE_EXCLUDES_HAZARD` is a
**test-invented literal with no authority behind it** and must **not** be seeded merely because a
test names it. (c) The remaining codes are AUTHORED from the demo's own facts — the clause
version's anchors `['LOTO','ZERO_ENERGY']`, the recalled precursor `DEMO-INC-0001`, and the
`blood_major` lattice — and then `test_reads.py`'s expected set is re-baselined to the authored
set with this ruling cited in the docstring. **This is a test losing to an authority, which the
ratified tiebreaker expressly permits ("either may lose").** What remains forbidden is choosing
the codes because they make the current line pass. The direction of travel must be:
authority → seed → test, never test → seed.

### R3 — Seeding rows alone does NOT clear blocker 1. The signature pins a constant today.

**Measured by this lead.** `gate_run.py:608` and `transitions.py:1065` both bind
`_sha("defeater-vocab")`. I computed `sha256(b"defeater-vocab")` =
`7ad8d49c2edd93f0a8fd3cd6b2a5d6cd225810805527a1a3f2f497aec819db3f` and confirmed it is
**byte-for-byte the value the deployed Cloud recorded** on its one signed disposition
(`GET-f116fc2724f1b968.json`, `signed.defeater_vocab_sha256`).
**Authority.** 0064: *"vocab_sha256 IS THE SAME VALUE ON EVERY ROW OF ONE GENERATION. It digests
the whole option set, not the row, so a signature that pins it pins the ALTERNATIVES the signer
declined as well as the one they chose."* `disposition.schema.json`: *"A disposition records the
same digest, so a later regeneration cannot silently reinterpret a past signature."*

**RULING.** A judge's signature must record the digest of the vocabulary that was **actually
offered**. Today it records the SHA-256 of the ASCII string `defeater-vocab`, which pins nothing
and would keep pinning nothing after the rows land. A test must assert
`disposition.defeater_vocab_sha256` equals the single distinct `defeater_option.vocab_sha256` for
that check, and that `disposition.defeater_code` is a MEMBER of the offered set. **A constant is
not a digest, and a wave that seeds rows without closing this has moved the visible half of the
defect and left the invisible half.**

### R4 — The sign path RESOLVES the digest from the database. It never recomputes it and never falls back.

**Authority.** The ratified repair of the credential incident, now in code:
`mainline_demo_api.credentials.resolve_credential_id` — the database owns the value, the
application reads it, the seed does not move. `tests/ci/test_demo_seed_is_frozen.py`'s docstring
states the principle in as many words.

**RULING.** `defeater_vocab_sha256` is resolved at sign time by reading
`mainline.defeater_option` for the check, in the same shape as the credential resolver. If that
read returns **no rows**, the sign path **refuses**, with a stated reason ("this check offers no
defeater vocabulary, so a signature cannot pin one"). It does not fall back to a constant.
**A silent fallback is how this shipped.**

### R5 — The frozen-seed guard is ALREADY RED at HEAD. The SEED is the side that moved. This wave pays the debt it did not incur.

**Measured.** Above, §1. `git log -- verticals/mainline/db/seeds/demo/demo_world.sql` →
last touched by `eefae1c` (and `8e6a195` before it). `git log -- tests/ci/test_demo_seed_is_frozen.py`
→ last touched by `c3e2254`, which is older. So the seed moved and the re-baseline that commit
owed was never paid, for **both** files.

**RULING.** This wave re-baselines both hashes **in the same commit** as its seed change, and the
commit message states, separately: (i) what THIS wave added to `demo_world.sql` and why; and
(ii) that `demo_permit.sql`'s hash and part of `demo_world.sql`'s drift are **not this wave's**
— they are `eefae1c`/`8e6a195`'s unpaid re-baseline, recorded rather than absorbed. Nobody may
report this red as "caused by the defeater work", and nobody may claim credit for fixing a
change they did not make.

### R6 — The brief's premise about 40001 is FALSE as stated, and the correction makes the work harder, not easier.

The brief says CockroachDB Cloud *"returns `40001 RETRY_SERIALIZABLE` under contention that
single-node Docker never produces."*

**Measured by this lead, on this workstation, against the local single-node CockroachDB
v26.2.5.** `SHOW default_transaction_isolation` → `serializable`. Six deliberate two-connection
races over two rows in a scratch table, each connection reading one key and updating the other:
**6 of 6 returned `40001 … TransactionRetryError: retry txn (RETRY_SERIALIZABLE)`.** The scratch
table was dropped afterwards; nothing was left behind.

**RULING.** 40001 is reproducible HERE. Therefore every retry loop this wave adds ships with a
**negative control that produces a real 40001 against the UNGUARDED code and shows the guarded
code survives it.** No worker may write "this cannot be tested without Cloud" — that sentence is
now measurably false and would be an untested guard dressed as a fix. What Cloud genuinely adds
is *rate and variety* (clock-uncertainty restarts, cross-node latency, `RETRY_WRITE_TOO_OLD`),
not existence. So the Cloud claim stays **unproven** and must be reported as unproven; local
green must never be allowed to imply it.

### R7 — This wave CANNOT reach CockroachDB Cloud from this workstation, and says so in those words.

**Measured.** No `CRDB_CLOUD_DSN`, `MAINLINE_*`, `COCKROACH_*`, `TRAPPOINT_*` or `CLOUD*`
variable exists in this environment (`Get-ChildItem Env:` filtered by those names returns
nothing). `.github/workflows/cloud-verify.yml:238` shows the DSN is a **GitHub repository
secret**, reachable by CI only. A Cloud cluster demonstrably exists — `demo-cloud/sql/cluster-fingerprint.txt`
records `mainline_demo`, user `mainline-sql`, CockroachDB CCL v26.2.5 — but its credential is not
here.

**RULING.** The suite is **not** run against Cloud from this workstation in this wave. No worker
may fabricate, infer or interpolate a Cloud result; no worker may print, log or reconstruct a
credential; no worker may attempt to obtain one. The Cloud half is delivered as (a) a CI lane the
founder can trigger, which runs the demo-api cluster suite against the secret when it is present
and fails loudly rather than skipping quietly when it is not, and (b) a written statement of
exactly what remains unproven. **The sentence "local green covers it" may not appear in any
deliverable of this wave.**

### R8 — The fixed scratch-database name is replaced by a CONTENT FINGERPRINT, not a random token.

**Measured.** `test_gate_run.py:143` — `SCRATCH_DB = os.environ.get("MAINLINE_W4_DATABASE",
"w_w4_api_transitions")`, a fixed default. The repository's own better pattern is three files
away: `demo-api/tests/conftest.py:341-358, 756` derives `w3_demo_api_{fingerprint}` from a
SHA-256 over every migration file and every `SEED_FILES` entry, precisely so *"a cached database
built from an older copy of it"* cannot be adopted silently.

**RULING.** Use the fingerprint pattern, not `uuid4`/`token_hex`. Random would fix the collision
and **lose** adoption; the fingerprint fixes the collision **and** makes it impossible to read a
seed edit against a stale database — which is the failure mode that already corrupted one
published "unstable" list. The `MAINLINE_W4_DATABASE` env override stays.

### R9 — NO migration in this wave. The missing foreign key is recorded as a finding, not closed by DDL.

**Measured.** `db/migrations/0066_disposition.sql` has **no** foreign key from
`mainline.disposition` onto `mainline.defeater_option`; `defeater_code` is `STRING NOT NULL` with
only `CONSTRAINT disposition_defeater_code_stated CHECK (defeater_code <> '')`. That is *why* an
empty vocabulary never refused anything and why beat 4 has been green over a defect since it was
written.

**RULING.** Do not add the FK now. Migrations are rendered from templates under a
`trappoint render --check` zero-diff assertion; a new constraint moves `migrations.lock.json`, the
schema fingerprint, and the dev/demo/prod parity gate, four days from the deadline, with no time
to verify the ripple. The gap is closed by the R3 assertion and **recorded as a named, dated
finding** in this plan and in `docs/STATE-OF-THE-BUILD.md`. **This ruling is not permission to
leave it unwritten**: a gap closed by a test and written down is honest; a gap closed by neither
is the thing this repository has been burned by most.

### R10 — DO NOT WRITE A RETRY LOOP. One already exists, is specified, and is spied on.

**Measured.** `packages/trappoint-core/src/trappoint_core/retry.py` exports `run_gate`,
`RetryPolicy` (capped exponential backoff, full jitter, `max_attempts=5`), `GateObserver`,
`RecordingObserver`. Its docstring states the contract: *"Run operation under the SQLSTATE
contract, retrying `40001` and only `40001` … operation must be the WHOLE transaction, from
`BEGIN`: `spec/errors.md` §2.1 forbids retrying a statement, because a statement replayed into a
poisoned transaction is not a retry of anything."* It raises `GateRefused` (the four refusal
codes, attempted exactly once ever), `AuthorisationDenied` (42501), `UnmodelledRefusal`, and
`RetryBudgetExhausted` (*"the transaction is undecided, which is not the same thing as
refused"*). `tests/concurrency/test_retry_taxonomy_spy.py` already watches it do this, in a
hermetic half and a live-cluster half. I confirmed `import trappoint_core.retry` succeeds in the
project venv.

**RULING.** Every retry this wave adds **in tests and in `scripts/`** uses
`trappoint_core.retry.run_gate`. Writing a second loop would be a second taxonomy to keep
correct and would silently un-specify `spec/errors.md` §2.1. Wrap the WHOLE transaction — a
`run_gate` around a single `execute()` inside an already-open transaction is not a retry, it is
the exact mistake the spec names.

### R11 — The Lambda handler is the ONE exception, and it is a hard constraint, not a preference.

**Measured.** `verticals/mainline/apps/demo-api/pyproject.toml:47-50` — the deployment package's
dependencies are `psycopg==3.3.4` and `psycopg-binary==3.3.4`, **and nothing else**, with the
comment *"NO boto3 … so the deployment package's behaviour does not depend on which boto3 the
runtime happens to ship this month"*, guarded by
`tests/test_envelope.py::test_no_web_framework_or_sdk_is_imported`.

**RULING.** `mainline_demo_api` (the runtime) must **not** gain a `trappoint_core` import. It
gets a small local retry inside the app package whose docstring names `spec/errors.md` §2.1 and
`trappoint_core.retry` as the specification it conforms to, plus a test asserting the two agree
on the taxonomy (retry 40001 only; refusal codes attempted once). Before and after, the worker
measures the built package bytes and re-runs `test_envelope.py` and `test_response_contract.py`:
the response ceiling `136 * 1024 = 139,264` is correct and stays, and the cost bound is stated in
bytes leaving the origin. **A retry loop that quietly grows the artefact past a ceiling has traded
one blocker for another.** This is needed because `POST /v1/demo/gate-run` is what two judges hit
at the same moment, which is the contention case the demo actually has.

### R12 — `qa/cluster-known-red.json` is NOT this lead's file.

`test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements` is
`groups[0].nodeids[58]`, and `unstable[0]` is
`test_transitions.py::test_gate_run_is_reachable_through_handle_transition` — a test that *"fails
only in suite and only sometimes"*, which is the exact signature W5's work targets.

**RULING.** Workers in this wave **fix** those tests and **report** the evidence; they do **not**
edit `qa/cluster-known-red.json`. It belongs to blocker 4's lead, and two leads editing one
inventory is how an inventory stops being true. Hand over: node id, before/after, and the
measured reason it now passes.

---

## 3 · WORKERS

Six workers. Paths are literally enumerated and **disjoint** — no two workers may write the same
file. A worker who believes it needs a file it does not own stops and reports; it does not edit.

| id | title | depends on |
|---|---|---|
| W1 | Seed the per-check defeater vocabulary, and pay the frozen-seed debt | — |
| W2 | Make the signature pin what was offered (resolve, refuse, never constant) | — |
| W3 | Walk the whole judge path through the real handler, and re-baseline `test_reads.py` | W1, W2 |
| W4 | Prove `trappoint_core.retry` is the primitive, and build the negative control | — |
| W5 | Apply the retry across every unguarded transaction; fix the scratch name | W4 |
| W6 | The Cloud lane and the honest statement of what is still unproven | W1–W5 |

**Owned paths, literally enumerated and disjoint.** No two workers write the same file.

* **W1** — `verticals/mainline/db/seeds/demo/demo_world.sql`; `tests/ci/test_demo_seed_is_frozen.py`
* **W2** — `verticals/mainline/apps/demo-api/src/mainline_demo_api/defeaters.py` (new);
  `…/src/mainline_demo_api/retry.py` (new); `…/src/mainline_demo_api/gate_run.py`;
  `…/src/mainline_demo_api/transitions.py`; `…/tests/test_defeaters.py` (new)
* **W3** — `verticals/mainline/apps/demo-api/tests/test_reads.py`;
  `…/tests/test_judge_can_sign.py` (new); `evidence/demo/judge-path-walk.json` (new)
* **W4** — `packages/trappoint-testkit/src/trappoint_testkit/txn.py` (new);
  `packages/trappoint-testkit/tests/test_txn.py` (new);
  `tests/concurrency/test_seed_permit_needs_retry.py` (new);
  `docs/diagnosis/retry-negative-control.md` (new)
* **W5** — `verticals/mainline/apps/demo-api/tests/test_transitions.py`;
  `…/tests/test_gate_run.py`; `…/tests/test_row_factory_contract.py`;
  `scripts/deploy/seed_demo.py`; `scripts/proof/gate_refusal.py`;
  `scripts/submission/seed_demo_state.py`; `scripts/qa/demo_suite_falsification.py`
* **W6** — `.github/workflows/cloud-verify.yml`; `docs/deploy/CLOUD-40001.md` (new);
  `docs/STATE-OF-THE-BUILD.md`

Verification protocol binding all six: report the demo-api `--crdb=reuse` numbers **BEFORE and
AFTER** your change, taken from `--junitxml` `tests=`/`failures=`/`errors=`/`skipped=`, never from
a terminal scroll. The suite is I/O-bound and silent for minutes; healthy runs have been killed
for looking hung. A fix that breaks a neighbour is worse than the defect.

---

## 4 · WHAT "DONE" MEANS FOR THIS WAVE

1. A judge can complete the story end to end: refusal → materialise → **choose a defeater** →
   **sign** → admission, walked through the real handler against the deployed seed, with each
   beat's evidence recorded.
2. The signature pins the vocabulary that was offered, not `sha256("defeater-vocab")`.
3. Every multi-statement transaction that will meet Cloud has a retry loop, and a real 40001
   proves each loop was needed.
4. The demo-api suite is **528 / 528 / 0 errors / 1 hermetic skip** under `--crdb=reuse`, and the
   frozen-seed guard is green because it was re-baselined with a reason, not because the seed was
   bent.
5. What is still unproven — the Cloud run — is written down in those words, and nowhere is local
   green allowed to stand in for it.
