<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MI01–MI30 catalogue vs the DDL that enforces it — divergence census

**Analyst:** `w6-mi-invariants` · **Date:** 2026-08-13 · **Mode:** READ-ONLY
**World:** `d_w6_mi_invariants`, chained by me, `271/271 applied · failed 0 · dirty False`,
fingerprint `43d73868eadbb813d2413def0b009957952bf2e9f0ca7b23618f0f0a65d11a96`,
CockroachDB CCL v26.2.5. Every SQLSTATE below was provoked by me on that node inside a
transaction and rolled back.

## Verdict

Thirty entries enumerated; **nine divergence pairs reported**, of which **2 HIGH,
4 MEDIUM, 2 LOW, 1 LATENT**. The headline is F-00: **MI15 is recorded `pending` — "the
`BEFORE INSERT` monotone guard does not exist" — and on the fully-chained schema that guard
exists and refuses with P0001, which I provoked with a positive control.** Its owning test
is red because that test applies a *band* of the migrations and stops short of the band that
builds the guard. `mi_ratchet red` cannot see the difference between a red measured on a
truncated schema and a red measured on the deployed one, so it reads the false red as the
law holding and MI15 stays `pending` forever. That is this wave's shape with the polarity
reversed: **a test agrees with the catalogue because both draw on the same partial-band
convenience path, and both diverge from what is actually deployed.**

The catalogue's two machine-checked projections are clean and
I could not break them: I re-derived `owning_migrations` from the `-- MI:` headers of all
271 files through the same 4096-byte window **without importing `mi_ratchet`**, and it is
**identical for all thirty** invariants; `MI-CATALOGUE.md` is **byte-identical** to a fresh
render; there are exactly thirty ids `MI01..MI30` with no gap and no duplicate; and **no
invariant has drifted to `40001`**. What is not clean is everything the ratchet does *not*
project. The catalogue's `instantiates:` column disagrees with **three** independent
recordings of the same fact and a test asserts the catalogue's version because it was
written from it (F-01). Four invariants name a mechanism that is absent from the applied
schema and the catalogue's prose confesses only two of them (F-02). And the red-before-green
gate the whole file exists for is **silent for 14 of the 21 `pending` invariants**, because
**6 of the 14 distinct test files the catalogue's selectors name do not exist on disk** and
`red` treats "no owning test at all" as the law holding (F-03). That is this wave's shape
one level up: the gate is green because it is structurally incapable of firing.

**Nothing here is a demo-path defect.** No finding below stops a judge running the demo; the
damage is to the artefact the submission leads with — the catalogue is simultaneously
*overstating* what is gated (F-03, F-04) and *understating* what is enforced (F-00), and
`ARCHITECTURE.md §16`, the document it declares itself a projection of, **is not in the
repository** (F-06), so four of its six columns have no arbiter at all.

---

## Inventory — all thirty, mechanism located in the applied schema, SQLSTATE provoked

`owning_migrations` re-derived independently for every row: **identical**, so the column is
omitted from the table and reported once in §"Pairs that hold".
`observed` = what `d_w6_mi_invariants` actually returned to my probe. `—` = not provoked by
me (reason in the last column).

| MI | status | mechanism named | in applied schema? | declared | **observed** | witness files exist? |
| --- | --- | --- | --- | --- | --- | --- |
| MI01 | enforced | revoked grants + BEFORE U/D trigger + RESTRICTIVE RLS | **yes** — 18 `append_only`/`fn_refuse_mutation` welds; 5 `restrictive` policies on `permit`, `change_request`, `disposition`, `mainline_meas.standing` | P0001 | **P0001** `MAINLINE: this table is append-only; write a new row` (UPDATE *and* DELETE on `mainline.person`) | 2 of 3 — `test_mi_triggers.py` **MISSING** |
| MI02 | enforced | `CHECK gate_closed_when_issued` + counter trigger | **yes** — `mainline.permit` | 23514 | **23514** `gate_closed_when_issued` | 0 of 2 — both **MISSING** |
| MI03 | pending | `CHECK identity_conserved_when_issued` | **yes** — `mainline.permit` | 23514 | **23514** `identity_conserved_when_issued` | 0 of 1 — **MISSING** |
| MI04 | pending | `CHECK conflicts_resolved_when_issued` | **yes** — `mainline.permit` | 23514 | **23514** `conflicts_resolved_when_issued` | 0 of 2 — both **MISSING** |
| MI05 | pending | `CHECK no_open_warrant_when_issued` | **yes** — `mainline.permit` | 23514 | **23514** `no_open_warrant_when_issued` | 0 of 1 — **MISSING** |
| MI06 | pending | `CHECK boundary_certified_when_issued` + **`fn_boundary_project`** | CHECK yes; **`fn_boundary_project` ABSENT from `pg_proc`** | 23514/P0001 | **23514** `boundary_certified_when_issued` | 1 of 3 |
| MI07 | pending | epoch-pin composite FK `ON UPDATE RESTRICT` | **yes** — `epoch_pin_permit`, `epoch_pin_cr` on `merge_record` | 23503 | **23503** `epoch_pin_permit` | 0 of 1 — **MISSING** |
| MI08 | pending | partial `UNIQUE … WHERE retracted_by IS NULL` | **yes** — `one_live_disposition` `ON mainline.disposition (check_id) WHERE (retracted_by IS NULL)` | 23505 | — behind `disposition_project`; see F-08 | 0 of 1 — **MISSING** |
| MI09 | pending | `merge_record` PK + `UNIQUE(permit_id, prev_seq)` CAS | **yes** — `merge_record_pkey (subject_kind, subject_id)`; the CAS is `linear UNIQUE (permit_id, prev_seq)` on `mainline.permit_event`, not on `merge_record` | 23505 | **23505** `merge_record_pkey` | 0 of 2 — both **MISSING** |
| MI10 | pending | FK to `subject_transition` | **yes** — `legal_edge`, `cr_legal_edge` | 23503 | **23503** `legal_edge` | 1 of 2 |
| MI11 | enforced | composite FK to `clearance_legal` | **yes** — `fk_carried_clearance`, `fk_clearance` | 23503 | **23503** `fk_carried_clearance` (+ positive control ADMITTED) | 2 of 3 |
| MI12 | pending | composite FK to `exposure_line` | **yes** — `fk_exposure (receipt_id, check_id)` on `mainline.disposition` | 23503 | — behind `disposition_project`; see F-08 | 0 of 1 — **MISSING** |
| MI13 | enforced | `CHECK inference_never_blocks` | **yes** — `mainline.blame_edge` | 23514 | **23514** `inference_never_blocks` | 1 of 1 |
| MI14 | enforced | `CHECK model_cannot_arm` | **yes** — `mainline.event` | 23514 | **23514** `model_cannot_arm` | 2 of 2 |
| MI15 | pending | **`BEFORE INSERT`** BLOODLINE guard | **yes** — `fn_clause_version_guard` (0141) welded by 0146; **but the trigger is `AFTER INSERT OR UPDATE`** — F-05. Its owning test never applies 0141 — **F-00** | P0001 | **P0001** `blame ancestry never shrinks — this version lowers sev_max below its parent` and `… lowers blood_size …` (+ positive control ADMITTED) | 2 of 2 |
| MI16 | enforced | `CHECK bonded_fatalities_all_blocking` + `fn_bonded_sev5` | **yes** — both | 23514 | **23514** `bonded_fatalities_all_blocking` (+ positive control ADMITTED) | 1 of 2 — `test_mi_recall_tables.py` **MISSING** |
| MI17 | pending | `CHECK candidates_conserved` | **yes** — `mainline_meas.recall_run` | 23514 | **23514** `candidates_conserved` | 0 of 2 — both **MISSING** |
| MI18 | enforced | `fn_recall_policy_anchored` | **yes** — welded `BEFORE INSERT` on `recall_run` | P0001 | **P0001** `recall policy is not anchored — a run may not cite an unanchored τ` | 1 of 2 — `test_mi_triggers.py` **MISSING** |
| MI19 | enforced | `CHECK no_orphan_controls` | **yes** — `mainline.doc` | 23514 | **23514** `no_orphan_controls` | 1 of 1 |
| MI20 | pending | `frontier_evidence` kind `CHECK` + `fn_frontier_guard` | **BOTH ABSENT** — and `owning_migrations: []`, nothing cites it | 23514/P0001 | **unprovokable — no object exists** | 0 of 1 — **MISSING** |
| MI21 | pending | `CHECK undetermined_never_blocks` | **ABSENT** from `pg_constraint` and from all 271 migrations | 23514 | **unprovokable — no object exists** | 0 of 1 — **MISSING** |
| MI22 | pending | merge-gate trigger | **yes** — `permit_merge_gate`→`fn_permit_merge_gate` (and `cr_merge_gate`) | P0001 | **P0001** `merge refused by mainline.fn_permit_merge_gate — no boundary certificate for this permit` | 0 of 2 — both **MISSING** |
| MI23 | pending | `CHECK only_tightenings_travel` | **ABSENT** from `pg_constraint` and from all 271 migrations (not even in a comment) | 23514 | **unprovokable — no object exists** | 0 of 1 — **MISSING** |
| MI24 | pending | `PRIMARY KEY (site_code, seq)` + in-txn derivation | **yes** — `ledger_leaf_pkey` | 23505 | **23505** `ledger_leaf_pkey`; the *event* CAS returns **P0001** `no predecessor event for the declared prev_seq` — see F-07 | 0 of 1 — **MISSING** |
| MI25 | pending | `fn_check_project`, raising on a missing closure | **yes** — welded `BEFORE INSERT` on `blocking_check` | P0001 | **P0001** `no blame closure for this clause version — cannot arm a check` | 0 of 2 — both **MISSING** |
| MI26 | pending | `fn_closure_guard` + append-only trigger + `agent_projector` grant | **yes** — function, `BEFORE INSERT` weld, and role `agent_projector` | P0001 | **P0001** `the first closure generation for a clause version must be zero` | 1 of 2 |
| MI27 | pending | `fn_disposition_project` | **yes** — welded `BEFORE INSERT` on `disposition` | P0001 | **P0001** `no such blocking check — a disposition cannot be filed against an obligation that does not exist` | 1 of 2 |
| MI28 | enforced | `ttl_enforced`, `bounded` | **yes** — `ttl_enforced`, `carried_bounded`, `predicate_bounded`, `non_trivial`, `watch_set_nonempty` | 23514 | **23514** `carried_bounded` (+ positive control ADMITTED) | 1 of 3 |
| MI29 | pending | `override_escalates` + `override_ledger` projection | **yes** — CHECK on `mainline.disposition`, table `mainline.override_ledger` | 23514 | — behind `disposition_project`; see F-08 | 0 of 2 — both **MISSING** |
| MI30 | pending | `CHECK cr_gate_closed_when_merged` | **yes** — `mainline.change_request` | 23514 | **23514** `cr_gate_closed_when_merged` | 0 of 2 — both **MISSING** |

**24 of 30 provoked.** The three I could not provoke *because the object does not exist*
(MI20, MI21, MI23) are the finding, not a gap in my measurement. The three behind
`disposition_project` (MI08, MI12, MI29) are F-08.

---

## Findings

### F-00 MI15 is held `pending` by a RED measured on a truncated schema; the deployed schema refuses — severity: **HIGH**

- **Divergence:**
  - `tests/integration/schema/test_mi_spine.py:1889` asserts, and FAILS with:
    *"PL-2 RED, as intended. MI15 is NOT enforced: a clause version whose parent carried
    sev_max=5 / blood_size=7 was accepted with sev_max=0 / blood_size=0. … **the BEFORE
    INSERT monotone guard does not exist.**"*
  - `verticals/mainline/db/migrations/0141_fn_clause_version_guard.sql:191` —
    `CREATE FUNCTION mainline.fn_clause_version_guard() RETURNS TRIGGER …`, welded by
    `verticals/mainline/db/migrations/0146_trg_clause_version_guard.sql`. **It does exist.**
- **Why the test cannot see it:** `test_mi_spine.py:145` declares
  `SPINE_BANDS = (("0024", "0031z"), ("0047", "0049"))` and its fixture applies only
  `BAND_FILES` (`:161`) plus a foundation band. `0141` and `0146` are **never applied** in
  that world. The test is not measuring the product's schema; it is measuring a prefix of it.
- **Command (mine, on the 271/271 node `d_w6_mi_invariants`):**
  `.venv/Scripts/python.exe <scratch>/provoke4.py`
- **Output (verbatim):**
  ```
  MI15-sev    want P0001/sev_max shrink       -> GOT P0001 constraint=None
              MAINLINE: blame ancestry never shrinks — this version lowers sev_max below its parent
  MI15-blood  want P0001/blood_size shrink    -> GOT P0001 constraint=None
              MAINLINE: blame ancestry never shrinks — this version lowers blood_size below its parent
  MI15-ctl    want 00000/positive control     -> **ADMITTED, NO REFUSAL**
  ```
  The positive control is what makes this evidence rather than arithmetic: the same insert
  with `blood_size` *raised* is admitted, so the P0001 is the guard acting, not a wall.
- **What a judge sees:** they open `MI-CATALOGUE.md`, read that MI15 — *"Blame ancestry never
  shrinks"* — is `pending`, meaning "no owning test has been observed to pass", then run one
  `INSERT` against the deployed database and watch it refuse. The catalogue that is the
  submission's centrepiece is **understating what the product enforces**, and the mechanism
  that is supposed to prevent exactly that kind of drift (`mi_ratchet red`) is the thing
  keeping the wrong answer in place: a `pending` invariant is only demanded for promotion
  when its tests **pass**, so a false red is permanent.
- **Same shape, needs the same check:** `test_mi_blame.py` runs `BAND_FIRST, BAND_LAST = 37, 39`
  (`tests/integration/schema/test_mi_blame.py:100`) while MI26's mechanism is
  `fn_closure_guard` (0108) welded at 0128j — the file says so itself at
  `test_mi_blame.py:28-30`. Its
  `test_mi26_red_the_monotone_guard_accepts_an_unrelated_severity_revision` also failed on my
  run. I provoked `fn_closure_guard` on the full chain and it **does** refuse
  (`P0001 … the first closure generation for a clause version must be zero`), but I did not
  reproduce that test's specific case, so I report MI26 as **needing the same
  full-chain re-measurement**, not as proven false-red.
- **What would have caught it:** the catalogue's own promotion standard —
  `mi_catalogue.yaml:84-86`, *"Does the enforcing object exist? Measured … on a CockroachDB
  v26.2.5 node with the whole chain applied"* — is written down and was applied to the seven
  invariants that were promoted. **It was never applied to the twenty-one that were not.**
  Nothing in `mi_ratchet` asks a red invariant whether its red was measured on the deployed
  schema. `locate_mechanisms` already knows the object exists (it prints it in the ledger)
  and no code path turns "object DEFINED **and** test RED" into a question.

### F-01 `instantiates:` disagrees with three other recordings, and a test locks in the catalogue's version — severity: **MEDIUM**

- **Divergence (four recordings of one fact):**
  - `verticals/mainline/db/invariants/mi_catalogue.yaml:283` — `MI08.instantiates: null`
    · `:308` — `MI10.instantiates: null` · `:553` — `MI21.instantiates: null`
    · `:668` — `MI27.instantiates: I09`
  - `spec/invariants/I09-exposure-binding.md:12` lists `MI08`, `MI12` — **and not `MI27`**
    · `spec/invariants/I04-linear-head.md:12` lists `MI10`
    · `spec/invariants/I08-certified-null.md:12` lists `MI21`
    · `spec/invariants/I02-projected-refusal.md:12` lists `MI27`
  - `spec/conformance/manifest.toml:212-217` (CF-12) ties `MI08` to `I09`
    · `:225-230` (CF-13) ties `MI10` to `I04` · `:312-317` (CF-19) ties `MI27` to `I02`
  - migration `-- I:` headers: `0011`, `0017a`, `0017b`, `0059` cite `I04` on files whose
    `-- MI:` line is `MI10`; `0066a`, `0159`, `0185d`, `0185f` cite `I09` on `MI08` files.
- **What holds them:** NOTHING. `scripts/mi_ratchet.py:446-455` (`_validate_instantiates`)
  checks only membership in `TRAPPOINT_INVARIANTS`, a frozenset **generated** at
  `scripts/mi_ratchet.py:195` as `f"I{n:02d}" for n in range(1, 17)`. It never opens
  `spec/invariants/`. Nothing in the tree compares the forward column with the reverse list.
- **And the test agrees with the catalogue because both were written from the same claim:**
  `tests/integration/schema/test_mi_ratchet.py:166-170` asserts
  `unmapped == {"MI08", "MI10", "MI21"}`, quoting the catalogue's own prose
  (`mi_catalogue.yaml:37-39`) as its justification. It is green, and it is green about a
  claim the spec, the conformance corpus and the migration headers all contradict.
  **This is the exact defect shape this wave exists to find.**
- **Command:**
  `.venv/Scripts/python.exe <scratch>/instantiates_diff.py`
- **Output (verbatim, trimmed):**
  ```
  === HARD DIVERGENCES ===
  ('MI08', None, ['I09'], 'DIVERGENT: catalogue says null, spec assigns I09')
  ('MI10', None, ['I04'], 'DIVERGENT: catalogue says null, spec assigns I04')
  ('MI21', None, ['I08'], 'DIVERGENT: catalogue says null, spec assigns I08')
  ('MI27', 'I09', ['I02'], "DIVERGENT: catalogue claims I09; I09's own file does not list MI27")

  === I ids with no MI in catalogue's forward map ===
  ['I08', 'I14', 'I15', 'I16']
  === I ids with no MI in spec's reverse map ===
  ['I15', 'I16']
  ```
- **What a judge sees:** they open `spec/invariants/I08-certified-null.md`, read
  "**MAINLINE schema invariants that instantiate it:** `MI21`", turn to
  `MI-CATALOGUE.md`, and MI21's `instantiates` column reads `—`. On the catalogue's own
  numbers **I08 has zero MAINLINE instances**, and the catalogue calls that absence "the
  interesting case". Both documents are in the public repo and both are cited by number.
- **What would have caught it:** NOTHING DOES. One test that parses
  `spec/invariants/I*.md:12` and asserts the two maps are mutual inverses would close it.

### F-02 Four invariants name a mechanism absent from the applied schema; the catalogue confesses two — severity: **MEDIUM**

- **Divergence:** `mi_catalogue.yaml:105-108` states, in the catalogue's own review note,
  that the ABSENT-object cases are exactly **MI06 and MI21**. Measured on a node with all
  271 migrations applied, there are **four**:

  | MI | line | object | applied schema |
  | --- | --- | --- | --- |
  | MI06 | `mi_catalogue.yaml:236` | `fn_boundary_project` | absent from `pg_proc` (documented) |
  | MI20 | `mi_catalogue.yaml:542` | `frontier_evidence`, `fn_frontier_guard` | **both absent — undocumented** |
  | MI21 | `mi_catalogue.yaml:554` | `undetermined_never_blocks` | absent (documented) |
  | MI23 | `mi_catalogue.yaml:619` | `only_tightenings_travel` | **absent — undocumented** |

  MI20 is worse than absent: `mi_catalogue.yaml:545` is `owning_migrations: []` — **no
  migration cites it on a `-- MI:` line at all** — and it has zero witnesses. MI23 declares
  `owning_migrations: ["0010", "0016"]` (`mi_catalogue.yaml:622`), which are
  `0010_type_control_delta.sql` and `0016_type_prop_state.sql`, two `CREATE TYPE` files;
  the string `only_tightenings_travel` occurs **nowhere in the 271 migrations, not even in
  a comment**.
- **Command:**
  `grep -rn "only_tightenings_travel\|frontier_evidence\|fn_frontier_guard\|undetermined_never_blocks" verticals/mainline/db/migrations/`
  and, against the applied node, `<scratch>/mech_in_db.py`.
- **Output (verbatim):**
  ```
  (grep: no output — zero hits across 271 files)

  MI20 [pending] sqlstate=('23514', 'P0001') mechanism='`frontier_evidence` kind `CHECK` + `fn_frontier_guard`'
        frontier_evidence: **NOT IN APPLIED SCHEMA**
        fn_frontier_guard: **NOT IN APPLIED SCHEMA**
  MI23 [pending] sqlstate=('23514',) mechanism='`CHECK only_tightenings_travel`'
        only_tightenings_travel: **NOT IN APPLIED SCHEMA**
  ```
- **What a judge sees:** MI23 is *"Only tightenings propagate across the fleet"* and MI20 is
  *"A weakening below the frontier cites only post-dating non-disposition evidence"* — two of
  the thirty safety claims the product makes about itself. A judge who asks "show me the
  object that refuses a loosening propagating across the fleet" gets no answer, and the
  catalogue's review note reads as though every such case had already been enumerated.
- **What would have caught it:** `mi_ratchet.py` already contains `locate_mechanisms`
  (`scripts/mi_ratchet.py:960-989`) which computes exactly this, but it is used **only to
  decorate a refusal message** (`_mechanism_report`, `scripts/mi_ratchet.py:1400`). No
  `check_violations` row asserts it. Nothing fails.

### F-03 The red-before-green gate is silent for 14 of the 21 `pending` invariants, because six selector files do not exist — severity: **HIGH**

- **Divergence:** `mi_catalogue.yaml:25-27` states the gate without qualification:

  > `mi-red    every` `pending` `invariant must have ≥1 owning test that currently FAILS.`

  `scripts/mi_ratchet.py:1460-1461` implements the opposite for the no-witness case:

  ```python
  for inv in catalogue.with_status("pending"):
      witnesses = resolution[inv.mi_id]
      if witnesses.is_unwitnessed:
          continue  # ← the law does not apply
  ```

  The flag that would make it apply, `--require-witness`
  (`scripts/mi_ratchet.py:2585-2589`, "*intended from K3*"), is **not passed by CI**:
  `.github/workflows/db-schema.yml:491` runs
  `uv run --frozen python scripts/mi_ratchet.py red --on-collect-error-red`.
- **Root cause, measured:** the invariants are unwitnessed because the files their
  selectors name are not in the tree. `validate_selector`
  (`scripts/mi_ratchet.py:1202-1216`) checks only that the string starts with `tests/`,
  ends with `.py`, has ≤1 `::` and no backslash. **It never checks that the path exists.**
- **Command:** a walk of every `owning_tests` selector against the filesystem.
- **Output (verbatim):**
  ```
  distinct selector FILES: 14
  OK       tests/integration/recall_schema/test_unweld.py -> ['MI16', 'MI18']
  OK       tests/integration/schema/test_mi_blame.py -> ['MI13', 'MI14', 'MI26']
  OK       tests/integration/schema/test_mi_boundary_override.py -> ['MI06', 'MI11', 'MI28']
  OK       tests/integration/schema/test_mi_clause_version_bloodline.py -> ['MI15']
  MISSING  tests/integration/schema/test_mi_disposition.py -> ['MI07','MI08','MI09','MI11','MI12','MI28']
  OK       tests/integration/schema/test_mi_event_severity.py -> ['MI14']
  OK       tests/integration/schema/test_mi_foundation.py -> ['MI01','MI10','MI11','MI27']
  MISSING  tests/integration/schema/test_mi_gate.py -> ['MI02','MI03','MI04','MI05','MI06','MI10','MI25','MI29','MI30']
  MISSING  tests/integration/schema/test_mi_periphery.py -> ['MI04','MI09','MI17','MI20','MI21','MI23','MI24','MI28']
  MISSING  tests/integration/schema/test_mi_projection.py -> ['MI02','MI06','MI22','MI25','MI26','MI27','MI29','MI30']
  MISSING  tests/integration/schema/test_mi_recall_tables.py -> ['MI16','MI17']
  OK       tests/integration/schema/test_mi_rls.py -> ['MI01']
  OK       tests/integration/schema/test_mi_spine.py -> ['MI15','MI19']
  MISSING  tests/integration/schema/test_mi_triggers.py -> ['MI01','MI18','MI22']
  ```
  and `mi_ratchet report`:
  ```
  MI03  pending   23514             18      0  unwitnessed, 1 not yet written
  MI20  pending   23514/P0001        0      0  unwitnessed, 1 not yet written
  …
  21 pending / 9 enforced
  ```
  The fourteen invariants for which **every** named file is absent — MI03, MI04, MI05,
  MI07, MI08, MI09, MI12, MI17, MI20, MI23, MI24, MI25, MI29, MI30 — are exactly the
  fourteen the ratchet reports as `unwitnessed`, and exactly the fourteen the red law
  skips.
- **What a judge sees:** `mi-red` exits 0 and the job summary
  (`.github/workflows/db-schema.yml:785-788`) prints, verbatim, *"`mi-red` REQUIRES at least
  one owning test of every pending invariant to be failing right now"*. Two thirds of the
  pending invariants have no test at all, and the board is green about them. A judge who
  deletes `CHECK identity_conserved_when_issued` from `0050_permit.sql` sees **`mi-red` and
  `mi-green` both stay green** — MI03's only selector already matches nothing, so neither of
  this catalogue's two laws changes colour. (Other lanes might still notice: the constraint
  name is a literal in `spec/conformance/manifest.toml:759`,
  `verticals/mainline/vertical.toml:212` and `tests/integration/schema/test_mi_spine.py:26`.
  The point is that **the catalogue that exists to hold MI03 would not**.)
- **What would have caught it:** `--require-witness` exists and is not wired; a
  file-existence assertion in `validate_selector` does not exist. **Cross-reference W4** —
  the root cause is "the test never ran", which is W4's, but the artefact that hides it is
  this catalogue's.

### F-04 `enforced` carries selectors to files that do not exist, which the catalogue calls fatal and `green` never checks — severity: **MEDIUM**

- **Divergence:** `mi_catalogue.yaml:60-61` — *"A selector matching nothing is reported as
  UNRESOLVED: legitimate while the owning worker has not landed, **fatal for anything
  `enforced`**."* `green_violations` (`scripts/mi_ratchet.py:1707-1727`) reads only
  `witnesses.is_unwitnessed`; the field that carries this fact, `Witnesses.unresolved`, is
  referenced at `scripts/mi_ratchet.py:1581`, `:1635-1636` and `:2005-2006` — **all three
  are report text**. No code path turns an unresolved selector into a violation.
- **Measured:** 6 of the 9 `enforced` invariants carry at least one selector to a
  nonexistent file — MI01 (`test_mi_triggers.py`), MI02 (both selectors), MI11
  (`test_mi_disposition.py`), MI16 (`test_mi_recall_tables.py`), MI18
  (`test_mi_triggers.py`), MI28 (`test_mi_disposition.py`, `test_mi_periphery.py`).
  MI02 is `enforced` with **zero** existing selector files; it stays green only because
  `@pytest.mark.mi("MI02")` discovers one test elsewhere.
- **What a judge sees:** `MI-CATALOGUE.md`'s witness table lists node ids under
  `tests/integration/schema/test_mi_gate.py` for a file that is not in the repository.
- **What would have caught it:** NOTHING DOES.

### F-05 MI15's mechanism says `BEFORE INSERT`; the applied trigger is `AFTER INSERT OR UPDATE` — severity: **LOW** (with a latent hazard)

- **Divergence:** `mi_catalogue.yaml:416` — ``mechanism: "`BEFORE INSERT` BLOODLINE guard"``.
  Applied schema:
  ```
  CREATE TRIGGER clause_version_guard AFTER INSERT OR UPDATE
    ON …mainline.clause_version FOR EACH ROW
    EXECUTE FUNCTION …mainline.fn_clause_version_guard()
  ```
- **Command / output:** `pg_get_triggerdef` on `d_w6_mi_invariants` (above), and the probe:
  ```
  MI15-sev    want P0001/sev_max shrink    -> GOT P0001  MAINLINE: blame ancestry never shrinks — this version lowers sev_max below its parent
  MI15-blood  want P0001/blood_size shrink -> GOT P0001  MAINLINE: blame ancestry never shrinks — this version lowers blood_size below its parent
  MI15-ctl    want 00000/positive control  -> **ADMITTED, NO REFUSAL**
  ```
- **What a judge sees:** nothing today — the refusal is real and it names MI15 in its own
  message. The claim about *when* it acts is wrong, and MI15 is `pending`, so a future
  promotion would be recorded against a timing this schema does not have.
- **Latent hazard worth naming:** `fn_clause_version_guard`'s UPDATE branch ends
  `RETURN NULL`. In an `AFTER` trigger that is ignored. If anyone "fixes" the divergence by
  moving the trigger to `BEFORE` to match the catalogue, `RETURN NULL` becomes **silently
  cancel the row** — a monotonicity guard that swallows writes instead of refusing them.
  It is masked today only because `append_only BEFORE UPDATE` already raises P0001 on
  `clause_version`.

### F-06 The catalogue's declared source document is not in the repository — severity: **MEDIUM**

- **Divergence:** `mi_catalogue.yaml:6` and `:118` name
  `ARCHITECTURE.md §16` as the authority, and `:36`, `:40`, `:41`, `:44` declare
  `statement`, `mechanism`, `sqlstate` and `headline` **verbatim from §16**.
- **Command:** `find . -name "ARCHITECTURE.md" -not -path "./.git/*"`
- **Output:** *(no output — the file does not exist anywhere in the tree)*. The repository
  already says so in its own voice at `docs/adr/0040-embedding-benchmark-titan-vs-cohere.md:114`:
  "*that document is not committed to*…".
- **What a judge sees:** four of the catalogue's six columns cite an authority they cannot
  be diffed against, `mi_ratchet check` cannot check them, and F-01's four-way disagreement
  has **no arbiter** — there is no document to ask which recording is right.
- **What would have caught it:** NOTHING DOES; `check_violations`
  (`scripts/mi_ratchet.py:2048-2064`) never opens `source`.

### F-07 MI→SQLSTATE is recorded twice and nothing compares them; the manifest is right where they differ — severity: **LATENT**

- **Divergence:** `mi_catalogue.yaml` `sqlstate:` per invariant vs
  `spec/conformance/manifest.toml` `expect_sqlstate` on every case carrying that `mi`.
  Measured disagreements: MI02 (`P0001` at CF-02/CF-03, `40001` at CF-43 —
  `manifest.toml:63,77,656`), MI07 (`P0001` at CF-10, `:184`), MI11 (`23514` at CF-27…CF-32,
  `:428,441,454,467,495`), MI24 (`P0001` at CF-16/17 `:268,282`; `00000` at CF-46 `:699`),
  MI25 (`23503` at CF-07, `:136`), MI27 (`23514` at CF-19, `:313`).
- **The 40001 case, checked because the catalogue forbids it:** `mi_catalogue.yaml:42-43`
  says *"NEVER 40001"* and `_validate_sqlstates` (`scripts/mi_ratchet.py:430-444`) enforces
  it — `mi_ratchet selftest` proves the law bites. **No catalogue entry has drifted to
  40001.** But `manifest.toml:656-667` (CF-43) is tagged `mi = ["MI02"]` with
  `expect_sqlstate = "40001"`. That case is `class = "retry"` and its own class taxonomy
  legitimately admits 40001, so this is a duplicated recording, **not a live defect** — it
  is reported here so the next wave does not "fix" a correct manifest against a narrower
  catalogue.
- **Where the manifest is measurably right and the catalogue narrow:** MI24's declared
  SQLSTATE is `23505` only. I provoked both arms of "dense and fork-free":
  ```
  MI24  ledger CAS  -> GOT 23505 constraint='ledger_leaf_pkey'
  MI24  event  CAS  -> GOT P0001  MAINLINE: no predecessor event for the declared prev_seq
  ```
  `fn_permit_event_chain` pre-empts the `linear UNIQUE (permit_id, prev_seq)` index, so the
  event-chain CAS returns **P0001**, exactly as CF-16/CF-17 record and the catalogue does not.
- **What holds them:** NOTHING. `check_violations` never reads the manifest; the conformance
  runner never reads the catalogue.

### F-08 Three invariants' declared SQLSTATE is unreachable as a *first* refusal, because `disposition_project` fires first — severity: **LOW**

- **Divergence:** MI08 (`23505` on `one_live_disposition`), MI12 (`23503` on `fk_exposure`)
  and MI29 (`23514` on `override_escalates`) all live on `mainline.disposition`. All three
  objects exist in the applied schema. But `disposition_project` is welded
  **`BEFORE INSERT`** and `fn_disposition_project` raises `P0001` the moment the row's
  `check_id` has no projectable closure:
  ```
  MI27 want P0001/fn_disposition_project -> GOT P0001
       MAINLINE: no such blocking check — a disposition cannot be filed against an
       obligation that does not exist
  ```
- **Consequence:** any test that writes a synthetic disposition without building the whole
  blame-closure chain observes `P0001` from MI27's projector, never MI08/MI12/MI29's own
  code. Their reserved selectors (`test_mi_disposition.py::test_mi08_*` etc.) name a file
  that does not exist (F-03), so no one has hit this yet — but whoever writes it will, and
  the catalogue does not warn them. Recorded so the next wave budgets a seeded fixture
  rather than discovering the ordering.
- **Honest limit of my measurement:** I did **not** provoke MI08, MI12 or MI29. I confirmed
  their objects exist with the right definitions and I confirmed the trigger that stands in
  front of them.

---

## Pairs checked and found to agree, with the mechanism that holds them

| pair | result | held by |
| --- | --- | --- |
| `owning_migrations` (30 rows) vs the `-- MI:` headers of all 271 migrations, re-derived by me through the same 4096-byte window **without importing `mi_ratchet`** | **IDENTICAL for all thirty**; 0 header problems; 271 files scanned | `migration_drift` in `check_violations` (`scripts/mi_ratchet.py:2053`), run by CI at `.github/workflows/db-schema.yml:142`. This is a real, working projection guard. |
| `MI-CATALOGUE.md` vs a fresh `render_markdown(catalogue)` regenerated into my scratch dir | **byte-identical**, 19266 == 19266 | `check_violations` (`scripts/mi_ratchet.py:2056-2062`) |
| thirty ids, `MI01..MI30`, in order | 30 present, **no gap, no duplicate** | `load_catalogue` ordering check + `test_mi_ratchet.py::test_a_gap_in_the_numbering_is_refused` |
| no invariant names `40001` | **none does** | `_validate_sqlstates` (`:430-444`); `mi_ratchet selftest` → `selftest: 26 laws bite`, incl. *"the loader refuses an invariant that names 40001"* |
| `headline: true` count | exactly 7 = {MI16, MI25, MI26, MI27, MI28, MI29, MI30} | `test_mi_ratchet.py::test_seven_headline_invariants_are_the_ones_sixteen_bolds` |
| `proposed:` MI31 vs the `-- proposes:` headers | agrees — `MI31 ['0041','0088','0114','0114a','0138','0138a']` | `proposal_drift` (`scripts/mi_ratchet.py:2054`) |
| parametrised node ids (7 owning selectors resolve to parametrised cases) | collapse correctly; **worst news wins** | `_normalise_nodeid` (`:1320-1322`) + `OutcomeCollector.pytest_runtest_logreport` (`:1287-1296`) — a green param cannot mask a red one |
| MI01's `RESTRICTIVE RLS` leg | **present** — 5 `restrictive` policies (`hold_blocks_delete`, `cr_delete_never`, `disposition_delete_never`, `peer_blind`, `standing_blind`) on 4 force-RLS relations. I nearly reported this absent; `pg_policies.permissive` is lower-case. Measured, not read. | the migrations themselves |
| `-- I:` headers citing `I17` (`0049y:5`, `0049z:5`) | **known and deliberate**, not a finding: `packages/trappoint-migrate/src/trappoint_migrate/cli.py:216-217` and `header.py:47-49` disable `strict_trappoint_ids` naming these two files | disclosed in code and README |
| `mi_ratchet check` | `catalogue integrity OK — 21 pending / 9 enforced`, exit 0 | — |
| `mi_ratchet selftest` | 26 laws bite, exit 0 | — |
| **`mi_ratchet green` against my own 271/271 node** | `enforced law holds over 39 node ids — 21 pending / 9 enforced`, **exit 0**, `9 failed, 542 passed in 1752.38s`. Every one of the 9 failures is a `pending` invariant's by-design-RED case, none is an `enforced` witness — so the enforced law genuinely holds. | `green_violations` (`scripts/mi_ratchet.py:1707-1727`) — and it refuses a SKIP, which matters, because all 542 passes were on a real cluster |

---

## Not reached (and why)

- **`mi_ratchet red` on a live cluster.** Started against `d_w6_mi_invariants`; it reached
  92% and then **hit pytest's 120 s per-test timeout inside
  `tests/integration/schema/test_mi_clause_version_bloodline.py:545`**, in a teardown that
  does `DROP DATABASE … CASCADE` — the local node is carrying the concurrent 24-worker wave
  and DDL is slow. `red` therefore produced no verdict on my run. Note for W4: **`mi_ratchet
  red`'s measurement path creates and drops databases on whatever `TRAPPOINT_DSN` points at.**
  F-03 does not depend on this run: it is a property of `red_violations`'s control flow and
  of six absent files, both established statically.
- **`mi_ratchet green` DID complete** (with `--pytest-arg=--timeout=900`, needed only because
  the local node is under the concurrent wave's load): `enforced law holds over 39 node ids`,
  exit 0, `9 failed, 542 passed in 1752.38s (0:29:12)`. The 9 failures are:
  ```
  test_mi_blame.py::test_pl2_red_sev_max_is_never_projected_from_the_closure
  test_mi_blame.py::test_mi26_red_the_monotone_guard_accepts_an_unrelated_severity_revision
  test_mi_boundary_override.py::test_pl2_red_fn_boundary_project_does_not_exist_yet
  test_mi_boundary_override.py::test_pl2_red_the_carried_use_projection_does_not_exist_yet
  test_mi_boundary_override.py::test_pl2_red_the_two_new_evidentiary_tables_have_no_append_only_trigger
  test_mi_boundary_override.py::test_pl2_red_nothing_yet_requires_a_cited_predicate_to_still_be_holding
  test_mi_event_severity.py::test_pl2_red_severity_revision_provenance_is_not_yet_projected
  test_mi_event_severity.py::test_pl2_red_one_person_can_still_downgrade_a_fatality
  test_mi_spine.py::test_mi15_a_version_may_not_shrink_its_ancestry          <-- F-00
  ```
  The last one is the F-00 case. `tests/integration/schema/test_mi_spine.py:1833-1834` gives
  it `@pytest.mark.requires_cluster` **and nothing else** — its docstring opens "RED BY DESIGN
  (PL-2)" but it carries no `pl2_red` marker, so `ci.yml`'s `RED_SELECTOR: "g4alpha or
  pl2_red"` does not deselect it and it fails inside the general regression lane. That is
  precisely the failure mode `pyproject.toml:144-157` registers the marker to prevent, and the
  file's *other* MI15 red case (`test_mi_spine.py:813
  ::test_pl2_red_mi15_bloodline_guard_does_not_exist_yet`) is named correctly.
  **The tool already knows and nothing fails on it** — `mi_ratchet pl2-red --verbose` prints:
  ```
  15 by-design-RED case(s) in 8 file(s) — these files should carry it:
    …
    tests/integration/schema/test_mi_spine.py  (2)
        test_mi15_a_version_may_not_shrink_its_ancestry
        test_pl2_red_mi15_bloodline_guard_does_not_exist_yet
  ```
  but `red_suite_violations` (`scripts/mi_ratchet.py:1756-1780`), the only part of `check`
  that looks at red-suite shape, inspects **only** `tests/integration/schema/test_mi_ratchet.py`.
  `pl2-red` is a report, not a gate, for the other seven files. **Cross-reference W4.**
- **MI08, MI12, MI29 provocation** — see F-08.
- **`ARCHITECTURE.md §16` column-by-column diff** — impossible; the document is not in the
  repository (F-06).
- **`spec/`'s I01–I16 content** is W10's; I checked only the `instantiates:` references
  into it, per the boundary ruling.
