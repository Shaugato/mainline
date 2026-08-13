<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DIVERGENCE CENSUS — lead plan

**Lead:** divergence-census-lead · **Date:** 2026-08-13 · **Mode:** READ-ONLY
**Deliverable of this wave:** a complete map of *duplicated truth* in this repository —
every place a load-bearing value is defined more than once — with, for each pair, an
**executed** determination of whether the two definitions agree TODAY and whether any
mechanism would make a future divergence fail loudly.

---

## 0. THE RULE EVERY ANALYST OBEYS

> **A separate 24-worker wave is editing this repository right now.**
> You are READ-ONLY. You may write **exactly one file**: your own output file under
> `docs/diagnosis/`. You may not edit, create, delete, format or `git`-mutate anything
> else — no `git add/commit/checkout/stash/restore`, no `terraform apply`, no formatters,
> no linters with `--fix`, no codemods, no mutating AWS calls. You may read anything, run
> read-only SQL, run `pytest`, run `terraform plan/validate/show`, run read-only `aws`/`gh`,
> and create scratch databases named `d_<your_id>` on the **local** node only.
> Never print a credential into your output or any file.

**Environment analysts share**

| thing | value |
| --- | --- |
| repo | `D:/CoackroachDBxAWS/mainline` (branch `master`, HEAD `2dc5c86`, ~18 dirty paths owned by the other wave) |
| python | `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe` |
| PYTHONPATH separator | `;` (Windows) |
| local cluster | `postgresql://root@localhost:26257/defaultdb?sslmode=disable` — CockroachDB CCL **v26.2.5**, healthy |
| demo-api import path | `verticals/mainline/apps/demo-api/src` |
| already-chained scratch DBs (read-only reference) | `w_w1`, `w_w2`, `w_w7`, `w_w1_demo`, `w_w3_demotruth`, `w3_demo_api_123396ff6486` — 112–113 tables across schemas `mainline` (72), `mainline_audit` (14), `mainline_meas` (12), `mainline_ops` (5), `mainline_qa` (3), `trappoint` (4) |
| chain applier | `scripts/chain/apply_chain.py` · 271 files in `verticals/mainline/db/migrations/` |
| demo seeder | `scripts/deploy/seed_demo.py` → `db/seeds/demo/demo_world.sql`, then `demo_permit.sql` |

**Do not trust another worker's scratch DB to be stable.** If you need a clean world, make
`d_<your_id>` and chain it yourself.

---

## 1. THE DEFECT SHAPE THIS WAVE IS HUNTING

All three NO-GO defects were the same thing:

> **A test agrees with the code because both draw on the same constant or the same
> convenience path, and both diverge from what is ACTUALLY DEPLOYED.**

Corollary that governs this census: **a pair that happens to agree today, with nothing
holding it in agreement, is a finding.** Report it as a *latent* instance with its own
severity. "They match" is only half an answer; the other half is "and here is what would
scream if they stopped matching" — or "nothing would".

**Prove agreement by executing something.** Reading two files and believing they match is
exactly how all three defects survived three review rounds.

---

## 2. WHAT THE LEAD ALREADY MEASURED (do not re-derive; do extend)

Commands and verbatim output are in §6. Summary:

1. **`scenario.py`'s entire default identifier family is seeded by nothing.**
   `from_env({})` yields `permit=077a6fdd-2167-559c-b2ff-8e3c8352504d`,
   `site=c333eb17-a6c8-5729-8e73-8d49a7ab3971`, `clause=512b662e-…`, `event=bf94c82a-…`.
   `grep -c` over **both** demo seed files returns **0** for all four. The seeds use a
   second, unrelated family — `dec0de00-000N-4000-8000-000000000001` — which is what
   `scripts/deploy/seed_demo.py:104-110` hard-codes and what
   `evidence/deploy/permit-id-agreement.json` proves is the only permit in Cloud.
2. **`scenario._selfcheck()` cannot detect this.** It compares the uuid5 derivation with
   the `EXPECTED` literals — i.e. the module against **itself**. It has never had any
   relationship to the seed. This is the canonical "mechanism that looks like a guard and
   guards nothing" and it is *still in the tree*.
3. **Terraform publishes only `MAINLINE_DEMO_PERMIT_ID` (+ `SIGNER_SUB`,
   `COUNTERSIGNER_SUB`).** `infra/modules/demo-api/main.tf:180-187` deliberately omits
   `MAINLINE_DEMO_SITE_ID`, arguing it is projected away by
   `mainline.fn_disposition_project`. `MAINLINE_DEMO_CLAUSE_UUID` and
   `MAINLINE_DEMO_EVENT_ID` are omitted with **no argument at all**. So a deployed Lambda
   receives one of four identifiers and falls back to three unseeded ones.
   `gate_run.py:607` does pass `resolved.scenario.site_id` into `_DISPOSITION_SQL`.
4. **`MAINLINE_DEMO_ALLOW_MUTATION`, `MAINLINE_DEBUG`, `MAINLINE_MAX_RESPONSE_BYTES` are
   read by the demo-api and published by no Terraform resource** — they appear only in
   prose in `variables.tf:773` and `README.md:634` as things `extra_environment` *could*
   carry.
5. **`testpaths` was widened** (`pyproject.toml:129-134` now includes
   `verticals/*/apps/demo-api/tests`) and the suite now collects **309** demo-api tests
   (measured, §6). The class of defect it hid is fixed *for that directory only*; whether
   any other test root is still invisible is W4's to settle.
6. Two more sha-recipe pairs of the beat-4 shape are visible without deep reading:
   `gate_run._sha("competency", signer_sub)` vs
   `demo_world.sql:102 digest('mainline-demo/competency/demo.signer','sha256')`, and the
   `cose`/`aaguid` digests at `demo_world.sql:126-135`. `0102_fn_disposition_project.sql:221`
   appears to *overwrite* `competency_sha256`, which — if true — makes the client value
   inert rather than wrong. **Which of the client-supplied disposition columns are
   projected away and which are load-bearing is the single highest-value question in this
   census**, because "inert" and "wrong" are indistinguishable by reading.

---

## 3. THE TEN SLICES

Disjoint by **subject matter**, not by directory. Each analyst writes **exactly one** file.

| # | id | subject | output file |
| --- | --- | --- | --- |
| 1 | `w1-demo-identity` | The demo scenario's **entity identifiers** — the two competing families | `docs/diagnosis/divergence-01-demo-identity.md` |
| 2 | `w2-derived-digests` | **Byte-valued** derived material: sha256/HMAC/`digest()`/canonical-JSON leaves, in more than one language | `docs/diagnosis/divergence-02-derived-digests.md` |
| 3 | `w3-env-contract` | Environment-variable contract: readers vs Terraform publishers vs what a deployed Lambda receives | `docs/diagnosis/divergence-03-env-contract.md` |
| 4 | `w4-connection-semantics` | Test-harness vs production **connection** semantics, and test-collection reachability | `docs/diagnosis/divergence-04-connection-semantics.md` |
| 5 | `w5-schema-expectations` | Schema expectations asserted in Python vs what the 271 migrations actually create | `docs/diagnosis/divergence-05-schema-expectations.md` |
| 6 | `w6-mi-invariants` | MI01–MI30 catalogue vs DDL enforcement, owning migrations/tests, SQLSTATEs, ratchet | `docs/diagnosis/divergence-06-mi-invariants.md` |
| 7 | `w7-bundle-and-site` | Public bundle manifest, captured frames and static site vs what the API actually serves | `docs/diagnosis/divergence-07-bundle-and-site.md` |
| 8 | `w8-contract-schemas` | `contracts/*.schema.json` vs the payloads the response builders emit | `docs/diagnosis/divergence-08-contract-schemas.md` |
| 9 | `w9-recorded-pins` | Version pins, image tags, lockfiles, region/model strings, and published counts recorded in more than one file | `docs/diagnosis/divergence-09-recorded-pins.md` |
| 10 | `w10-spec-vs-impl` | TRAPPOINT `spec/` (I01–I16, wire, errors, custody, conformance) vs `packages/trappoint-*` | `docs/diagnosis/divergence-10-spec-vs-implementation.md` |

### Boundary rulings (memorise; they are what keeps ten reports disjoint)

* **W1 vs W2.** If both sides of the pair are **UUIDs naming a demo entity** (permit, site,
  clause, event, check, receipt, recall-run, disposition, commit) → **W1**. If the value is
  **bytes produced by a hash/HMAC/canonicalisation recipe** (credential ids, competency
  digests, COSE keys, AAGUIDs, chain digests, canon hashes, merged_commit's byte layout) →
  **W2**. `merged_commit` is bytes → W2; the `commit` uuid it is built from → W1.
* **W1 vs W3.** W1 owns *which value is right*; W3 owns *whether the value reaches the
  process at all* (published/unpublished/typo'd env names, defaults, precedence).
* **W5 vs W6.** W5 owns **names, types, nullability, FK targets** referenced by application
  code. W6 owns **enforcement mechanisms** (CHECK/trigger/RLS/function) claimed by the MI
  catalogue and the SQLSTATE each produces.
* **W6 vs W10.** MI01–MI30 and `mi_ratchet.py` → W6 (including the `instantiates:` column's
  references to I01–I16). `spec/invariants`, `spec/wire`, `spec/errors.md`,
  `spec/custody`, `spec/conformance` and their `packages/trappoint-*` implementations → W10.
* **W7 vs W8.** W7 owns the bundle's **metadata, file inventory, digests, route keys** and
  the **bytes the static site serves**. W8 owns **schema-vs-payload validation**, including
  validating the captured frame bodies against `contracts/*.schema.json`.
* **W2 vs W9.** A digest that is *computed* → W2. A digest, tag or version that is
  *recorded as a literal in two files* → W9.
* **W4 vs everyone.** Any finding whose root cause is "the test never ran" or "the test ran
  against a connection production never uses" is W4's, even if the symptom is in another
  slice. Cross-reference rather than duplicate.

---

## 4. THE REPORT FORMAT EVERY ANALYST USES

One file, this shape. No preamble, no restating the brief.

```markdown
# <slice title> — divergence census

## Verdict
<one paragraph: how many pairs enumerated, how many DIVERGENT, how many LATENT,
 how many HELD. If the slice is clean, say so plainly and stop.>

## Inventory
| # | value | definition A (file:line) | definition B (file:line) | status | held by | severity |
(status ∈ DIVERGENT | LATENT | HELD.  "held by" = the executable mechanism that
 fails when they stop agreeing, or the word NOTHING.)

## Findings
### F-<id> <one-line title> — severity: CRITICAL|HIGH|MEDIUM|LOW|LATENT
- **Divergence:** `path/a.py:123` says X · `path/b.sql:45` says Y
- **Command:** <the exact command>
- **Output:** <verbatim, trimmed, with the decisive line intact>
- **What a user or judge sees:** <the concrete failure, not "could fail">
- **What would have caught it:** <name the mechanism, or say NOTHING DOES>

## Pairs checked and found to agree, with the mechanism that holds them
## Not reached (and why)
```

**Severity discipline.** `CRITICAL` = a judge running the demo hits it.
`HIGH` = wrong behaviour on a path the demo does not walk, or a security/cost consequence.
`MEDIUM` = wrong but self-evident, or requires an unusual input. `LOW` = cosmetic.
`LATENT` = agrees today, nothing holds it. **Ranking a cosmetic mismatch as critical costs
the next wave more than it saves.** A clean slice is a real result; inventing findings to
look busy is the worst possible outcome of this wave.

---

## 5. SHARED RECIPES

**Import the demo-api without installing it**

```bash
cd /d/CoackroachDBxAWS/mainline
PYTHONPATH="verticals/mainline/apps/demo-api/src" .venv/Scripts/python.exe -c "import mainline_demo_api"
```

**Make and chain your own world** (do not disturb another worker's)

```bash
.venv/Scripts/python.exe -c "import psycopg;c=psycopg.connect('postgresql://root@localhost:26257/defaultdb?sslmode=disable',autocommit=True);c.execute('CREATE DATABASE IF NOT EXISTS d_<your_id>')"
.venv/Scripts/python.exe scripts/chain/apply_chain.py --help     # read its flags first
.venv/Scripts/python.exe scripts/deploy/seed_demo.py --help
```

**Ask the database rather than the file**

```sql
SELECT table_schema, table_name, column_name, data_type, is_nullable
  FROM information_schema.columns WHERE table_schema LIKE 'mainline%';
SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'mainline.disposition'::regclass;
```

**Never** run `pytest` with `-p no:randomly`-style flags that change the harness, and never
pass `--fix`, `-W error::DeprecationWarning` or anything that writes.

---

## 6. LEAD'S OWN MEASUREMENTS (verbatim)

```
$ .venv/Scripts/python.exe -c "import psycopg; ... SELECT version()"
CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/...

$ PYTHONPATH=verticals/mainline/apps/demo-api/src python -c "from mainline_demo_api import scenario as s; sc=s.from_env({}); ..."
permit  077a6fdd-2167-559c-b2ff-8e3c8352504d
site    c333eb17-a6c8-5729-8e73-8d49a7ab3971
clause  512b662e-1208-51a4-be59-ecb4f3ca085f
event   bf94c82a-1aac-5cb0-87c9-b371d958f158

$ grep -c "c333eb17\|077a6fdd\|512b662e\|bf94c82a" db/seeds/demo/demo_world.sql db/seeds/demo/demo_permit.sql
verticals/mainline/db/seeds/demo/demo_world.sql:0
verticals/mainline/db/seeds/demo/demo_permit.sql:0

$ grep -oE "'[0-9a-f-]{36}'" db/seeds/demo/demo_permit.sql | sort -u
'dec0de00-0001-…' 'dec0de00-0004-…' 'dec0de00-0005-…' 'dec0de00-0006-…'
'dec0de00-0007-…' 'dec0de00-0008-…' 'dec0de00-0009-…' 'dec0de00-000a-…'

$ python -m pytest verticals/mainline/apps/demo-api/tests --collect-only -q | tail -1
309 tests collected in 0.48s

$ grep -rn "ALLOW_MUTATION|MAX_RESPONSE_BYTES|MAINLINE_DEBUG" infra/ scripts/deploy/
infra/modules/demo-api/README.md:634   (prose only)
infra/modules/demo-api/variables.tf:773 (prose only)
→ published by no Terraform resource.
```

---

## 7. WHAT "DONE" MEANS FOR THIS WAVE

Ten files under `docs/diagnosis/`, each with an **Inventory table whose every row has a
status and a `held by` column**, and findings ranked honestly. The union of those tables is
the artefact the founder asked for: the complete list of places where this repository
believes two things at once, so that one subsequent wave can fix all of them instead of
discovering them one NO-GO at a time.
