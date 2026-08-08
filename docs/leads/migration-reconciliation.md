<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MIGRATION RECONCILIATION — the ruling

**Spawned:** 2026-08-08, on a cross-domain seam failure.
**Scope:** `verticals/mainline/db/migrations/` (121 files), `packages/trappoint-sql/templates/`,
`packages/trappoint-sql/refvertical/sql/`, and the two runners that read them.
**Authority:** `ARCHITECTURE.md` §18 (order) and §5/§16 (semantics) win on design. This document
decides only what §18 leaves open, and every decision is numbered `MR-n` with its justification.
**Binding on:** every worker in every domain, including the five kernel workers not yet dispatched.

---

## 0. What actually happened, measured not assumed

The collision report (`_migration_collisions.json`, 24 numbers) is **not the failure**. It is a
symptom, it contains false positives, and it misses the two failures that actually stop the chain.

I ran the real discovery code (`trappoint_migrate.discovery.discover`) over the tree. Ground truth:

| Population | Count | Convention | Author |
|---|---|---|---|
| Carries `-- @rendered-by  trappoint render` | **44** | `NNNN[a-z]_slug.sql` | **produced by `packages/trappoint-sql/templates/*.j2`** |
| Hand-authored `.up.sql` | **49** | `NNNN[a-z]_slug.up.sql` | datamodel (`dm-foundation`, `dm-spine`, `dm-blame`), custody |
| Hand-authored plain `.sql` | **28** | `NNNN[a-z]_slug.sql` | recall, algorithms |
| | **121** | | |

**The single most important fact in this incident: the kernel side of every collision is rendered
output.** It was never hand-written into the migrations directory. `trappoint render` writes it
there from `packages/trappoint-sql/templates/`, `vertical.toml` says
`output_dir = "verticals/mainline/db/migrations"`, and `trappoint render --check` is a zero-diff CI
assertion. **Deleting a rendered file does not resolve a collision — the next render recreates it.**
Any plan that says "delete the kernel's 0006a…0006i" is a plan that fails on the next `render`.

### The two hard failures (the tree does not discover at all)

Both raise `MigrationTreeInvalid` before a single statement reaches the cluster. Verified by running
the runner's own code against the tree:

1. **Seven duplicate version stems.** `_version_of()` strips `.up.sql` and `.sql` alike, so
   `0010_type_control_delta.up.sql` and `0010_type_control_delta.sql` both yield version
   `0010_type_control_delta`. Same for `0011`–`0016`. The runner refuses:
   `two files claim version '0010_type_control_delta'`.
2. **Two filenames with a second dot.** `_VERSION_RE = ^(\d{4})([a-z]*)_([a-z0-9_]+)$` does not admit
   `.`, so `0031_clause_embedding.fallback.sql` yields the stem `0031_clause_embedding.fallback` and
   the runner refuses the **whole directory**. Same for `0031a_clause_embedding_ann.fallback.sql`.
   These two files also would have been *applied as migrations* had the regex been looser — a
   fallback variant sitting in the apply path is worse than a broken build.

### Five silent lint failures nobody reported

`statement_count()` says these carry two top-level statements, against the non-negotiable
one-statement-per-file rule (a multi-statement file is not atomic, so `dirty` becomes undiagnosable):

`0086_thymogate_certificate.sql` · `0114_fn_cue_prefix_project.sql` ·
`0138_trg_cue_prefix_project.sql` · `0139_trg_candidate_project.sql` ·
`0211_fn_delta_witness_guard.sql`

`0139` and `0211` are worse than untidy: each contains a `CREATE FUNCTION` inside a file numbered in
a *trigger* band, which inverts §18's stratification.

### Two false positives in the collision report

`0029` (`0029_clause_version.up.sql` + `0029a_clause_version_trgm.up.sql`) and `0072`
(`0072_ledger_intake.up.sql` + `0072a_ledger_intake_hlc_comment.up.sql`) are **not collisions**.
Both pairs have one owner and use the letter suffix exactly as ruling D7 intends. The report grouped
on the leading four digits; the runner orders on the whole stem. Do not "fix" these.

### The collisions that are real

Twenty numbers where two domains implemented the same objects: `0001`–`0009` (schemas, roles,
revokes, grants), `0010`–`0016` (the seven types), `0017` (subject_transition), `0018`
(clearance_legal), `0021`–`0023` (site/person/signing_credential). Every one is
**rendered-vs-authored**, and that is what makes the ruling in §1 decisive rather than arbitrary.

---

## 1. MR-1 — THE ARCHITECTURE RULING (binding, forward and backward)

> **`verticals/mainline/db/migrations/` has exactly two kinds of file, and every number in the
> sequence belongs to exactly one of them: RENDERED (emitted by a template in
> `packages/trappoint-sql/templates/`, never hand-edited) or AUTHORED (written directly in the
> vertical, never emitted). The seam is drawn by OBJECT, not by worker or by band, and the object
> test is: _would a second TRAPPOINT vertical need this object to pass `trappoint-conform`?_
> If yes it is SUBSTRATE and it is a template. If no it is VERTICAL and it is authored.**

**Why.** Three reasons, in descending order of force.

1. **It is already true on disk and mechanically enforced.** 44 files carry the rendered banner;
   `check_units()` already reports `missing` / `diff` / `stale`; `render_binding()` already refuses
   when two templates emit one filename. The alternative ruling ("both author directly, partitioned
   number space") requires *deleting the render engine's output contract* and is a larger change to
   more code than the reconciliation itself.
2. **A hand-authored twin of a rendered file is permanently red.** `trappoint render --check` is a
   zero-diff assertion. A `.up.sql` twin is not a diff, so `--check` passes while the *runner*
   refuses the tree — the exact failure mode where CI is green and the deploy is dead.
3. **The substrate claim is the product.** §1.1 of `kernel.md` ships a reference vertical so "the
   extension mechanism is exercised the day it is written". `permit`, `blocking_check`,
   `disposition` and `merge_record` authored directly into MAINLINE would make the reference
   vertical a second, divergent implementation of the gate — i.e. a template engine with an audience
   of one, which is the thing that decision exists to prevent.

**MR-2 · The object list, fixed.** SUBSTRATE is exactly: the five schemas; the nine roles and the
privilege floor; the seven enum types; `subject_transition` (+seed); `clearance_legal` (+seed);
`person`; `signing_credential`; `permit`; `change_request`; `permit_clause`; `cr_clause`;
`permit_event`; `cr_event`; `blocking_check`; `exposure_receipt`; `exposure_line`;
`receipt_expiry`; `defeater_option`; `disposition`; `disposition_citation`; `override_ledger`;
`merge_record` + its two epoch-pin FKs; `refusal_ledger`; the projection function/trigger family;
the merge procedures and merge-gate triggers; the gap-free CAS append function. **Everything else in
MAINLINE is VERTICAL**: the commit DAG, `doc`/`clause`/`clause_version`/`clause_band`, the embedding
sidecars, blame, events, `site`, `retention_class`, `adm_decision_class`, recall, the custody ledger,
measurement, fixity, fleet, governance, ops, `delta_witness`, and every MAINLINE view and policy.

**MR-3 · Where the two plans die.** `datamodel.md` §3's banding table allocated `0001–0023`
(`dm-foundation`), `0050–0065` (`dm-gate`) and `0066–0071` (`dm-disposition`) to hand-authored
`.up.sql`. **Those three bands are revoked.** `dm-foundation` keeps only `retention_class`,
`adm_decision_class` and `site`; `dm-gate` and `dm-disposition` are dissolved and their content is
contributed as **template input and constraint text** to the kernel workers `subject-and-pin` and
`obligation-and-clearance`. Every semantic those plans carry — GSAC (DM-2), the MATCH SIMPLE epoch
pin (DM-1), DM-4's JSONB-free `CHECK`s, DM-10's explicit names, DM-12's deterministic seeds —
survives **inside the templates**, and DM-5's behaviour-not-mechanism test rule is what makes that
survival checkable. `datamodel.md` §3's bands at and above `0130` are also revoked (see §4).

**MR-4 · Grants: both, not either.** `datamodel.md` DM-7 pulled grants out of migrations entirely;
the templates emit `0009a`–`0009e`. Both are right about different things, so: the rendered
`0009a`–`0009e` are the **privilege floor** — the minimum without which migration `0024` cannot run,
idempotent and re-asserted on every apply. `GRANTS.yaml` remains the **full matrix**, applied by
`trappoint-migrate grants apply` and drift-checked by the privilege probe. The DM-7 sentence moves
into the `0009e_default_privileges_floor.sql` header; the marker file `0009_grants_are_not_migrations.up.sql`
is deleted because a `SELECT 'a sentence'` is not a migration.

---

## 2. MR-5 — THE ONE FILENAME CONVENTION

```
NNNN[a-z]_lower_snake_slug.sql
```

Stated exactly:

* **`NNNN`** — exactly four decimal digits, zero-padded, allocated by the table in §3/§4 and by its
  machine-readable form `verticals/mainline/db/migrations.allocation.toml`.
* **`[a-z]`** — an optional **single** lowercase letter. Ordering is lexicographic on the whole
  stem, so `0006a < 0006b < 0007` and `0119a < 0120`. It has exactly two legal uses:
  1. **Multi-statement slot.** One logical object that needs more than one top-level statement:
     `0058_blocking_check.sql` then `0058a_bc_open_index.sql`.
  2. **Band overflow.** A full band absorbs new work by suffixing its own last number rather than
     renumbering a neighbour: `0119a_fn_explain_refusal.sql` when `0120` belongs to someone else.
     *This is the mechanism that prevents this incident from recurring: a worker that runs out of
     numbers suffixes, it never borrows.*
  * `x` is reserved for comment/marker-only files (`0009x_covenant_comment.sql`) and sorts last.
* **`_lower_snake_slug`** — `[a-z0-9_]+`. **No second dot, ever.** `.fallback.sql`, `.variant.sql`,
  `.v2.sql` fail `_VERSION_RE` and make the entire directory undiscoverable (measured, §0).
  Capability variants live in `verticals/mainline/db/ext/<topic>/` and are selected by a render-time
  switch (kernel D5), never by a file in the apply path.
* **Exactly one top-level SQL statement per file.** Enforced by `statement_count()`.
* **`.sql` and nothing else.** There is **no down-migration counterpart and there never will be**:
  `discover()` raises on `.down.sql`, and DM-14 forbids one at or below the protected floor.
  **`.up.sql` is therefore banned** — not as a style preference but because it names a counterpart
  that is illegal by construction, and because a suffix chain is what let two conventions coexist
  invisibly. It is removed from `MIGRATION_SUFFIXES` the moment the renames land.
* Every file keeps the **REUSE SPDX header** and the four linted keys `MI:`, `I:`,
  `COUNSEL-GATED:`, `RATIONALE:`.
* Rendered files additionally carry `-- @rendered-by  trappoint render` and **are never hand-edited**
  — a change to a rendered file is a change to its template followed by a re-render of **both**
  bindings (MAINLINE and `refvertical`).

**Why `.sql` and not `.up.sql`:** the render engine's `-- @file` sentinels already emit `.sql`; 72 of
121 files already comply; and `discovery.py` documents `.up.sql` as backwards tolerance, not as the
contract ("accepted because the repository already carries files written in that convention").

### MR-6 — How this is made mechanically enforceable (four locks)

1. **`migrations.allocation.toml`** — the §3/§4 table as data: `number-range → owner → mode`.
   The prose below is its rendering; the file is the authority.
2. **`trappoint migrate lint`** gains three rules: (a) filename must match
   `^\d{4}[a-z]?_[a-z0-9_]+\.sql$`; (b) every file's number must fall in a band the allocation file
   grants to its `mode` (a hand-authored file in a `rendered` band is a lint failure, and so is the
   reverse); (c) `.up.sql` is a failure. Rule (c) is **red until the renames land** — that is
   deliberate and it is the PL-2 artefact for this reconciliation.
3. **`stem_collisions()` is promoted** from advisory to a `trappoint render --check` failure. It is
   the function that would have caught this incident on day one and it was returning its finding to
   nobody.
4. **`trappoint render --check`** stays the zero-diff assertion, and `check_units()`'s existing
   `stale` finding is what makes "delete a template" a visible act rather than a silent one.

---

## 3. THE ALLOCATION — tables and seeds (`0001`–`0099`)

One owner per band. **`Mode` is binding: it says which directory the file is written in.**

| Band | Owner | Mode | Contents |
|---|---|---|---|
| `0001`–`0018` | kernel `render-and-foundation` | **RENDERED** | schemas ×5, roles ×9, revokes ×5, ownership ×5, privilege floor ×6, covenant comment, types ×7, `subject_transition` +seed, `clearance_legal` +seed |
| `0019`–`0020a` | datamodel `dm-foundation` | AUTHORED | `retention_class` (`0019`), `adm_decision_class` (`0020`), `site` (`0020a`) |
| `0021`–`0023` | kernel `render-and-foundation` | **RENDERED** | `person`, `signing_credential`, its partial index |
| `0024`–`0031` | datamodel `dm-spine` | AUTHORED | `commit_obj`, `commit_edge`, `ref`, `doc`, `clause`, `clause_version` (+`0029a` trgm), `clause_band`, `clause_embedding` |
| `0032`–`0039` | datamodel `dm-blame` | AUTHORED | `activity_node`, `event`, `event_edge`, `control_failure`, `event_severity_revision`, `blame_edge`, `clause_blame_closure`, `clause_blame_current` |
| `0040`–`0046` | recall `recall-ddl-triggers` | AUTHORED | `event_cue`, two vector sidecars, BM25 ×3, `event_bond` |
| `0047`–`0049` | datamodel `dm-spine` | AUTHORED | `control_series`, `carriage`, `identity_residue` |
| `0049a`–`0049z` | algorithms | AUTHORED | `delta_witness` (`0049a`) — the algorithms table annexe |
| `0050`–`0053` | kernel `subject-and-pin` | **RENDERED** | `permit`, `change_request`, `permit_clause`, `cr_clause` |
| `0054`–`0057` | datamodel (ex-`dm-gate`) | AUTHORED | `asset_edge`, `permit_boundary`, `permit_slice`, `boundary_certificate` |
| `0058`–`0064` | kernel `obligation-and-clearance` | **RENDERED** | `blocking_check` (+indices `0058a`/`0058b`), `permit_event`, `cr_event`, `exposure_receipt`, `exposure_line`, `receipt_expiry`, `defeater_option` |
| `0065`–`0065z` | datamodel (ex-`dm-gate`) | AUTHORED | `mechanism_predicate`, `predicate_revocation` |
| `0066`–`0068` | kernel `obligation-and-clearance` | **RENDERED** | `disposition` (+`0066a` one-live partial unique), `disposition_citation`, `override_ledger` — G0-gated |
| `0069`–`0070` | datamodel (ex-`dm-disposition`) | AUTHORED | `carried_disposition`, `carried_disposition_use` — G0-gated |
| `0071`–`0071z` | kernel `subject-and-pin` (`0071`–`0071b`), kernel `quickrefuse` (`0071c`–`0071d`) | **RENDERED** | `merge_record`, `epoch_pin_permit`, `epoch_pin_cr`, `refusal_ledger`, its index |
| `0072`–`0079` | custody | AUTHORED | ledger intake/leaf/node/checkpoint, cosignature, unwitnessed debt, custodian attestation, sequencer lease |
| `0080`–`0089` | recall | AUTHORED | `mainline_meas.*` recall/silence/certificate family |
| `0090`–`0099` | datamodel `dm-periphery` | AUTHORED | fixity, fleet, governance, frontier, contradiction pair, `mainline_ops.*` |

## 4. THE ALLOCATION — functions, triggers, views, policies (`0100`–`0199`)

`ARCHITECTURE.md` §18 sized functions at `0100`–`0114` and triggers at `0115`–`0139` before the
merge procedures, `explain_refusal()` and the CAS helper existed. Kernel **D8** extended the ranges;
`datamodel.md` §3 instead *remapped* them to `0130`–`0199` / `0200`–`0279`.

**MR-7 · D8's extension is adopted; datamodel's remap is revoked.** D8 extends an open range without
moving an anchor. The remap moves anchors that three other domains have already committed against
(`0112`–`0114`, `0136`–`0139` are on disk and correct), and it opens a `0200+` space §18 never
defined, which is where the algorithms domain then went. Extending is free; renumbering costs
everything.

| Band | Owner | Mode | Contents |
|---|---|---|---|
| `0100`–`0109` | kernel `projection-triggers` | **RENDERED** | `fn_check_project`, `fn_check_materialised`, `fn_disposition_project`, `fn_disposition_close`, `fn_disposition_retract_only`, `fn_permit_event_chain`, `fn_cr_event_chain`, `fn_refuse_mutation`, `fn_closure_guard`, `fn_site_role` |
| `0110`–`0114` | recall | AUTHORED | `fn_candidate_project` (`0110`), `fn_recall_policy_anchored`, `fn_bonded_sev5`, `fn_cue_prefix_project` (+`0114a` coarse) |
| `0115`–`0119` | kernel `merge-gate-and-core` | **RENDERED** | `fn_permit_merge_gate`, `fn_cr_merge_gate`, `proc_merge_permit`, `proc_merge_change_request`, `fn_ledger_cas_append` |
| `0119a`–`0119z` | kernel `quickrefuse` | **RENDERED** | `fn_explain_refusal` (`0119a`), `fn_refusal_ledger_guard` (`0119b`) |
| `0120`–`0129` | kernel `projection-triggers` | **RENDERED** | the nine projection triggers |
| `0130`–`0135` | kernel `merge-gate-and-core` (`0130`–`0132`), kernel `quickrefuse` (`0133`) | **RENDERED** | `trg_permit_merge_gate`, `trg_cr_merge_gate`, `trg_refusal_ledger_append_only` |
| `0136`–`0139` | recall | AUTHORED | `trg_recall_policy_anchored`, `trg_bonded_sev5`, `trg_cue_prefix_project` (+`0138a` coarse), `trg_candidate_project` |
| `0140`–`0144` | datamodel `dm-functions-triggers` + algorithms | AUTHORED | vertical PL/pgSQL functions; `fn_delta_witness_guard` = `0140` |
| `0145`–`0149` | datamodel `dm-functions-triggers` + algorithms | AUTHORED | vertical triggers; `trg_delta_witness_guard` = `0145` |
| `0150`–`0154` | algorithms | AUTHORED | `mainline.*` business views; `v_safe_direction_current` = `0150` |
| `0155`–`0169` | datamodel `dm-views-rls` | AUTHORED | `mainline_audit` views, ≤25 rows / ≤10 KiB each |
| `0170`–`0179` | datamodel `dm-views-rls` | AUTHORED | `mainline_qa` views |
| `0180`–`0198` | datamodel `dm-views-rls` | AUTHORED | `CREATE POLICY` (RLS), read-facing tables only, every forced table gets its write policy |
| `0199` | datamodel `dm-views-rls` | AUTHORED | `ALTER TABLE exposure_receipt ADD CONSTRAINT fk_silence` — the deferred cycle |
| `0200`+ | **UNALLOCATED** | — | **No file may use it.** The algorithms `0200`–`0219` annexe is revoked. |

### MR-8 · Forward-binding rulings for the five pending kernel workers

Each declared a number in `workers.json` that this allocation moves. **These are the numbers, and
each of these workers writes a TEMPLATE plus its rendered outputs — not a hand-authored migration.**

| Worker | Declared | **Ruling** | Why it moves |
|---|---|---|---|
| `subject-and-pin` | `0050a_permit.sql`, `0050b_permit_scope_index.sql`, `0071a_merge_record.sql`, `0071b/c_epoch_pin_*` | `0050_permit.sql`, `0050a_permit_scope_index.sql`, `0051_change_request.sql`, `0052_permit_clause.sql`, `0053_cr_clause.sql`, `0059_permit_event.sql`, `0060_cr_event.sql`, `0071_merge_record.sql`, `0071a_epoch_pin_permit.sql`, `0071b_epoch_pin_cr.sql` | **`0050a` is void.** The letter suffix is for a companion statement or a band overflow, never for the primary object of a free number. Leaving `0050` and `0071` empty forfeits the anchors §18 names and every cross-reference that cites them. |
| `obligation-and-clearance` | `0058a_blocking_check.sql`, `0058b/c` indices, `0066a_disposition.sql`, `0066b` | `0058_blocking_check.sql`, `0058a_bc_open_index.sql`, `0058b_bc_open_cr_index.sql`, `0061_exposure_receipt.sql`, `0062_exposure_line.sql`, `0063_receipt_expiry.sql`, `0064_defeater_option.sql`, `0066_disposition.sql`, `0066a_one_live_disposition.sql`, `0067_disposition_citation.sql`, `0068_override_ledger.sql` | **`0058a`/`0066a` as primaries are void**, same reason. `0058`/`0066` are §18 anchors cited by `mi_catalogue.yaml` (`owning_migrations: [0058, 0130]`). |
| `projection-triggers` | `0100`–`0109` fn, `0120`–`0128` trg | **CONFIRMED UNCHANGED.** | The only pending worker whose declaration survives intact. It is also the only one that did not reach past its band. |
| `merge-gate-and-core` | `0111`–`0115` fn, `0135`–`0136` trg | **`0115_fn_permit_merge_gate.sql`, `0116_fn_cr_merge_gate.sql`, `0117_proc_merge_permit.sql`, `0118_proc_merge_change_request.sql`, `0119_fn_ledger_cas_append.sql`, `0130_trg_permit_merge_gate.sql`, `0131_trg_cr_merge_gate.sql`** | `0112`/`0113`/`0114` and `0136` are **occupied on disk** by recall (`fn_recall_policy_anchored`, `fn_bonded_sev5`, `fn_cue_prefix_project`, `trg_recall_policy_anchored`). Four live collisions. `0115`–`0119` is contiguous and exactly the right size. |
| `quickrefuse` | `0116a/b` table+index, `0117`/`0118` fn, `0137` trg | **`0071c_refusal_ledger.sql`, `0071d_refusal_ledger_index.sql`, `0119a_fn_explain_refusal.sql`, `0119b_fn_refusal_ledger_guard.sql`, `0133_trg_refusal_ledger_append_only.sql`** | `0116` is a **function** slot — a `CREATE TABLE` there inverts §18's stratification and would be created after triggers that could read it. `0137` is occupied by `trg_bonded_sev5`. The table joins the substrate table space behind `merge_record`; the functions take the band-overflow suffix. |

---

## 5. PER-FILE DISPOSITION

Rules used, in order: **(a)** if a rendered twin exists, the rendered file survives and any semantic
the authored twin holds and the template lacks is **merged into the template**, then re-rendered
into *both* bindings; **(b)** if no twin exists and the object is VERTICAL, the file survives and is
renamed to MR-5; **(c)** nothing is deleted whose semantics are not first shown to exist elsewhere.

### 5.1 Superseded by a rendered twin — DELETE the `.up.sql`, MERGE first (20 files)

| Authored file (delete) | Superseded by (rendered) | Semantics that must survive |
|---|---|---|
| `0001_role_mainline_owner.up.sql` | `0006b_role_owner.sql` | `CREATE ROLE IF NOT EXISTS mainline_owner WITH NOLOGIN` — already byte-identical in the template. Its long unassumability rationale is worth transplanting into the template header. |
| `0002_schema_mainline.up.sql` | `0001a_schema_mainline.sql` + `0008a_owner_business.sql` | `AUTHORIZATION mainline_owner` at creation vs `CREATE … IF NOT EXISTS` then `ALTER … OWNER TO`. **Verified on the local v26.2.5 node: both end with `nspowner = mainline_owner`.** The transient window is inside one run, before any table exists, so nothing can be created under the wrong owner and survive. Rendered wins; the template header must carry this argument so it is not re-litigated. |
| `0003_schema_mainline_meas.up.sql` | `0002_schema_meas.sql` + `0008b_owner_meas.sql` | as above |
| `0004_schema_mainline_audit.up.sql` | `0003_schema_audit.sql` + `0008c_owner_audit.sql` | as above |
| `0005_schema_mainline_qa.up.sql` | `0004_schema_qa.sql` + `0008d_owner_qa.sql` | as above |
| `0006_schema_mainline_ops.up.sql` | `0005_schema_ops.sql` + `0008e_owner_ops.sql` | as above |
| `0007_revoke_public_on_mainline_schemas.up.sql` | `0007a`–`0007e_revoke_public_*.sql` | one five-schema `REVOKE` → five one-schema `REVOKE`s. Strictly better under one-statement-per-file. |
| `0008_revoke_create_on_public_schema.up.sql` | **nothing yet** | ⚠ **UNIQUE SEMANTIC.** `REVOKE CREATE ON SCHEMA public FROM public;` has no rendered equivalent. Without it any principal that can connect can create objects in the evidentiary database and be reached through `search_path`. **Must be added to `templates/0006_roles.sql.j2` as `0009f_revoke_create_public_schema.sql` before this file is deleted.** |
| `0009_grants_are_not_migrations.up.sql` | `0009e_default_privileges_floor.sql` | the DM-7 sentence (grants are cluster state; `GRANTS.yaml` is the matrix) moves into the `0009e` header. A `SELECT 'sentence'` is not a migration. |
| `0010`–`0016_type_*.up.sql` (7) | `0010`–`0016_type_*.sql` | **enum values and their order are byte-identical in all seven pairs** — verified. The rendered form adds `IF NOT EXISTS`, verified idempotent on the local node. Pure duplicates; delete without merge. |
| `0017_subject_transition.up.sql` | `0017a_subject_transition.sql` + `0017b_subject_transition_seed.sql` | the authored file has **no seed at all**; rendered ships the 18-row lattice for both subject kinds. Constraint names change to the substrate's (`pk_subject_transition`, `subject_transition_kind_known`) — the conformance corpus asserts exact names, so the substrate's names are the exhibit. |
| `0018_clearance_legal.up.sql` | `0018a_clearance_legal.sql` + `0018b_clearance_legal_seed.sql` | rendered ships the 21-row seed with the **three deliberately absent cells** (`blood_major/accept_residual`, `blood_fatal/mechanism_absent`, `blood_fatal/accept_residual`) — DM-17's conservative default, correct as rendered. ⚠ **MERGE INTO TEMPLATE:** the authored file's `policy_version_not_blank` and `approved_by_sub_not_blank` `CHECK`s, which the template lacks. |
| `0022_person.up.sql` | `0021_person.sql` | ⚠ **MERGE INTO TEMPLATE:** `signer_sub_stated CHECK (signer_sub <> '')` and `identity_source_stated CHECK (identity_source <> '')`. Rendered already has the `competency_sha256` length-32 check the authored file lacks — keep both sides. |
| `0023_signing_credential.up.sql` | `0022_signing_credential.sql` + `0023_signing_credential_index.sql` | ⚠ **MERGE INTO TEMPLATE:** `signer_sub_stated CHECK (signer_sub <> '')`. Rendered already has `credential_revocation_reasoned CHECK ((revoked_at IS NULL) = (revoke_reason IS NULL))`, which the authored file lacks — keep both. The inline `INDEX by_signer` becomes the standalone `0023`; identical predicate. |

### 5.2 Kept, renamed `.up.sql` → `.sql` (29 files)

`0019_retention_class` · `0020_adm_decision_class` · `0021_site` **→ renumbered `0020a_site.sql`**
(because `0021` is the substrate's `person`; `site` must precede `0024`, and every FK to it —
`0072`, `0074`, `0075`, `0077`, `0079` — is far downstream) · `0024_commit_obj` · `0025_commit_edge` ·
`0026_ref` · `0027_doc` · `0028_clause` · `0029_clause_version` · `0029a_clause_version_trgm` ·
`0030_clause_band` · `0031_clause_embedding` · `0032_activity_node` · `0033_event` ·
`0034_event_edge` · `0035_control_failure` · `0036_event_severity_revision` · `0047_control_series` ·
`0048_carriage` · `0049_identity_residue` · `0072_ledger_intake` · `0072a_ledger_intake_hlc_comment` ·
`0073_ledger_leaf` · `0074_ledger_node` · `0075_ledger_checkpoint` · `0076_cosignature` ·
`0077_unwitnessed_debt` · `0078_custodian_attestation` · `0079_sequencer_lease`.

Rename only — **no SQL body may change**. Header `requires:` lines that cite the old foundation
numbers must be corrected to the rendered ones (`0001a` business schema, `0002` meas, `0003` audit,
`0004` qa, `0005` ops).

### 5.3 Moved out of the apply path (2 files)

`0031_clause_embedding.fallback.sql` → `verticals/mainline/db/ext/vector_fallback/clause_embedding_table.sql`
`0031a_clause_embedding_ann.fallback.sql` → `verticals/mainline/db/ext/vector_fallback/clause_embedding_ann_index.sql`

They break `_VERSION_RE` and would otherwise be *applied*. DR-1's GT-06 fallback is a render-time
capability switch (D5), not a file that sits next to the primary in the apply path.

### 5.4 Split (5 files) and relocated (3 files)

| File | Action |
|---|---|
| `0086_thymogate_certificate.sql` | split → `0086_thymogate_certificate.sql` (`CREATE TABLE`) + `0086a_recall_policy_thymogate_fk.sql` (`ALTER TABLE`) |
| `0114_fn_cue_prefix_project.sql` | split → `0114_fn_cue_prefix_project.sql` + `0114a_fn_cue_coarse_project.sql` |
| `0138_trg_cue_prefix_project.sql` | split → `0138_trg_cue_prefix_project.sql` (embedding) + `0138a_trg_cue_prefix_project_coarse.sql` |
| `0139_trg_candidate_project.sql` | split → **`0110_fn_candidate_project.sql`** (the function moves into the function band) + `0139_trg_candidate_project.sql` (trigger only) |
| `0205_delta_witness.sql` | rename → `0049a_delta_witness.sql` (a `CREATE TABLE` must live in the table space, after `0029 clause_version`, before the gate) |
| `0207_v_safe_direction_current.sql` | rename → `0150_v_safe_direction_current.sql` |
| `0211_fn_delta_witness_guard.sql` | split + relocate → `0140_fn_delta_witness_guard.sql` + `0145_trg_delta_witness_guard.sql` |

### 5.5 Untouched

The 44 rendered files (except the four re-rendered in §5.1), and `0040`–`0046`, `0080`–`0085`,
`0087`, `0088`, `0112`, `0113`, `0136`, `0137` — already compliant; header `requires:` corrections
only.

---

## 6. WORKER DECOMPOSITION

Eight workers. **File lists are literal and strictly disjoint** — this is the exact discipline whose
absence caused the incident, so there are no globs, no bands and no ranges anywhere in a worker's
`files_owned`. Dependency order: **W1 → W2 → {W3, W4, W5, W6, W7} in parallel → W8.**

| # | id | Owns |
|---|---|---|
| 1 | `mr-allocation-and-guard` | the allocation TOML and the four locks in the two runners |
| 2 | `mr-template-merge` | three templates + the seven rendered outputs their change touches, both bindings |
| 3 | `mr-foundation-twins` | the 20 superseded `.up.sql` foundation files, plus `0019`/`0020`/`site` |
| 4 | `mr-spine-blame-rename` | `0024`–`0036`, `0047`–`0049` renames + the two fallback moves |
| 5 | `mr-custody-rename` | `0072`–`0079` renames |
| 6 | `mr-recall-splits` | recall's four multi-statement splits and the misplaced function |
| 7 | `mr-algorithms-relocate` | `0205`/`0207`/`0211` renames and the split |
| 8 | `mr-lock-and-plans` | `migrations.lock.json` and the binding ruling block appended to five lead plans |

Full briefs, `files_owned` and `done_when` are carried in the structured output that accompanies this
document and are the dispatch contract.

---

## 7. RISKS I AM ACCEPTING

| # | Risk | Why I accept it | Detector |
|---|---|---|---|
| MRR-1 | The ruling dissolves `dm-gate` and `dm-disposition` and moves ~35 tables' worth of DDL from a datamodel worker to two kernel workers. That is a large reassignment eleven days from the deadline. | The alternative is two implementations of the gate, which is the substrate claim's negation. The DDL itself does not change — only the file it is typed into. GSAC, the MATCH SIMPLE pin and the named `CHECK`s carry over verbatim as template text. | `trappoint-conform --profile trappoint-ref` green proves the templates work for a second binding; `--profile mainline` proves they work for this one. |
| MRR-2 | Constraint names change on `subject_transition`, `clearance_legal`, `person`, `signing_credential` (authored names lose to rendered names). The constraint name is the courtroom exhibit and the conformance corpus asserts it exactly. | Only one set can be the exhibit, and it must be the one a second vertical also produces. The corpus is not yet written for these four tables, so the cost is zero today and unbounded in a month. | `conformance-corpus` (W9 of kernel) asserts exact names; `test_mi_foundation.py` asserts DM-10's no-system-generated-names rule. |
| MRR-3 | Re-rendering to add `0009f_revoke_create_public_schema.sql` could perturb bytes in the 25 other files `0006_roles.sql.j2` emits, silently pulling files outside W2's ownership. | Contained by making it W2's `done_when`: `trappoint render` must report exactly one added file and zero changed files among `0006*`–`0009x`. An additive template edit that changes a neighbour's bytes is a wrong edit, and it is visible in one command. | `trappoint render --check` + `git status`. |
| MRR-4 | Lint rule (c) — `.up.sql` is a failure — is red between W1 and the completion of W3/W4/W5. | Deliberate. It is this reconciliation's PL-2 artefact: a guard that was observed red is a guard that asserts something. The window is one dispatch wave. | The CI job name is the evidence; its red run URL goes in the commit body. |
| MRR-5 | `0049a_delta_witness` and `0150_v_safe_direction_current` cross what were previously other workers' bands, using the letter-suffix and the extended tail rather than renumbering. A reader may read that as the same band-borrowing that caused the incident. | It is the opposite: the allocation file grants `0049a`–`0049z` and `0150`–`0154` to algorithms **explicitly and exclusively**, and lint rule (b) enforces it. Band borrowing failed because it was undeclared, not because it happened. | `migrations.allocation.toml` + `trappoint migrate lint`. |
| MRR-6 | Header `requires:` lines across ~35 renamed files cite foundation numbers that moved. These are comments; nothing executes them. | Accepted as documentation debt with a bounded fix: each rename worker corrects the `requires:` lines in the files it owns, and nothing else reads them. | A grep in `done_when`; no runtime effect. |
| MRR-7 | `0200`+ is left unallocated rather than reserved for a future domain. | A number space with no owner is exactly what produced two conventions. An unallocated range that lint refuses is safer than a range someone can assume into. | lint rule (b). |

---

## 8. VERIFICATION — the one command that ends this

Against the **local** node (`postgresql://root@localhost:26257/defaultdb?sslmode=disable`, v26.2.5,
2.4 s for DDL + 5 000 vector inserts versus >120 s on Cloud Basic — the inner loop is local):

```
trappoint render --binding verticals/mainline/vertical.toml --check
trappoint render --binding packages/trappoint-sql/refvertical/vertical.toml --check
trappoint migrate lint  --root verticals/mainline/db/migrations
trappoint migrate bootstrap --dsn "$LOCAL_DSN"
trappoint migrate up        --dsn "$LOCAL_DSN" --root verticals/mainline/db/migrations
```

Reconciliation is done when all five are green, `discover()` returns **one** file per version, and
`stem_collisions()` returns the empty list. Pin `ALTER RANGE default CONFIGURE ZONE USING
gc.ttlseconds = 4500` in the init step — local defaults to 14400 and is therefore *more permissive*
than Cloud; where they differ, configure local to the stricter value.

---

*Migration reconciliation lead, 2026-08-08. One convention, one authoring mode per number, one owner
per band, and a lint that fails before a human has to notice. The collision check reported zero
because it compared strings; the replacement compares a file against a declaration.*
