<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The conformance census — every case, by name

**Generated** 2026-08-10T07:59:48Z · **spec** `1.0.0-rc.1` · **profile** `mainline` · **schema** `mainline` · **run-id** `cert-final`

**Cluster** `CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)`  
**Database** `postgresql://root@127.0.0.1:26257/prod_w9?sslmode=disable`  
**Manifest** `spec/conformance/manifest.toml` — 71 cases declared

> **CHECKED AGAINST ITS OWN SOURCE, 2026-08-14 by D3 — it agrees, and it is still a
> 2026-08-10 reading.** Two different questions, answered separately because they are
> routinely conflated:
>
> **1. Does this document match the artefact it is generated from?** *Yes, exactly.*
> `qa/conformance-census.json` reads `totals: {passed: 10, failed: 6, cannot_run: 55,
> skipped: 0, pending: 0, error: 0}`, `selected: 71`, and `completeness.complete: true` with
> *"every declared case carries a status, nothing is PENDING, nothing ERRORed, and every
> non-PASSED case carries a reason naming an object"*. Every total below reproduces. **No
> digit in this document is edited.**
>
> **2. Is it a statement about the tree as it stands today?** *No, and it never claimed to
> be.* It was taken `2026-08-10T07:59:48Z` against database `prod_w9` under run-id
> `cert-final`. The migration chain, the seeds and the demo world have all moved since —
> `mainline.defeater_option` alone was seeded into two deployed seed files on 2026-08-14.
> **A conformance census is only a claim about the schema it was run against**, which is why
> the header carries the version, the profile and the DSN. Re-derive with the
> `census_command` recorded in the artefact — `scripts/qa/run_conformance_census.py --build
> --run-id <id>` — and publish the new run beside this one rather than over it.
>
> **10 of 71 is not a good number and this page has always said so** (*"This run is not
> green, and publishing it is the point"*). Nothing in this note improves it, and nothing in
> this wave is entitled to.

```
D:\CoackroachDBxAWS\mainline\.venv\Scripts\trappoint-conform.exe --dsn postgresql://root@127.0.0.1:26257/prod_w9?sslmode=disable --profile mainline --autodetect-requires --json --run-id cert-final
```

---

## What a green case entitles the reader to say

`spec/conformance/README.md` §9 is the authority and it is quoted rather than paraphrased. **It does entitle you to say:** the database refused every history this specification says it must refuse, by the exact mechanism it names, at the named profile and version; and that no refusal in the run fell outside the modelled taxonomy. **It does not entitle you to say:** that the vertical's obligations are the right obligations; that severity was scored correctly; that a disposition is honest or that a signature was considered; that retrieval was exhaustive; that the system is secure against a privileged operator; or that any human process improved. Every one of those is out of scope, and a conformance badge implying otherwise is the kind of claim a competent expert takes apart in one question.

So a PASS below means one thing and one thing only: for that history, the database issued the exact SQLSTATE and the exact exhibit the manifest names. It is not a statement that the obligation modelled is the right obligation, that a severity was scored well, or that anything outside the named refusal works. A claim of conformance MUST cite version and profile, which is why both are in the header above and in every machine-readable row of [`qa/conformance-census.json`](../../qa/conformance-census.json).

**This run is not green, and publishing it is the point.** 10 of 71 cases passed. The census exists to account for the other 61 by name, each with a reason naming an object a reader can go and look at. `docs/HONESTY.md` said this suite demonstrated no conformance case; this document is the first time it has been executed end to end against a migrated MAINLINE schema.

---

## Totals

| status | n | what it means |
|---|---:|---|
| **PASS** | 10 | the database refused exactly as the manifest says it must |
| **FAIL** | 6 | it did not — including a relation reported absent, named here |
| **CANNOT RUN** | 55 | nothing was asked of the gate: the legal world would not build, or a declared capability was measured absent |
| **SKIPPED** | 0 | a capability token was unmet and nobody looked (should not occur under --autodetect-requires) |
| **PENDING** | 0 | the manifest declares the case and no implementation exists |
| **ERROR** | 0 | the runner itself broke — always fatal |
| — | **71** | cases selected for profile `mainline` |

**Census verdict: COMPLETE** — every declared case carries a status, nothing is PENDING, nothing ERRORed, and every non-PASSED case carries a reason naming an object.

The census's own gate is *completeness*, not greenness: zero `PENDING`, zero `ERROR`, and a reason naming an object on every non-pass. A red census that accounts for all 71 cases is the deliverable; a green one that accounted for 30 would be worth nothing.

### The schema the suite ran against

`trappoint.schema_migration` carries **271** row(s) (`applied` 271); the tree holds **271** `.sql` file(s). Every case below that names a missing relation is measured against exactly this state, not against an aspiration.

## Reproducibility

`census_digest` = `sha256:e641fa2113f6112e9568b0814dc2b811992202eeaf0967b3b7498cfb06a9026b` — sha256 over the sorted `id=status` rows.

Not compared this run — the earlier census carried run_id 'w9-20260810', this one 'cert-final'; a comparison across run ids would compare different tenancies. Re-run with `--run-id cert-final` and this section becomes the comparison.

## Capability probe

16 of 23 `requires` tokens are satisfied on database `prod_w9` (schema `mainline`), measured against `pg_class`, `pg_namespace`, `pg_roles` and `pg_policies`. **No token was declared satisfied by hand** — the census never passes `--requires`.

| token | kind | object | satisfied | detail / reason |
|---|---|---|:--:|---|
| `mainline.blame_edge` | relation | `mainline.blame_edge` | yes | table mainline.blame_edge |
| `mainline.boundary_certificate` | relation | `mainline.boundary_certificate` | yes | table mainline.boundary_certificate |
| `mainline.carriage` | relation | `mainline.carriage` | yes | table mainline.carriage |
| `mainline.carried_disposition` | relation | `mainline.carried_disposition` | yes | table mainline.carried_disposition |
| `mainline.clause_version` | relation | `mainline.clause_version` | yes | table mainline.clause_version |
| `mainline.cosignature` | relation | `mainline.cosignature` | yes | table mainline.cosignature |
| `mainline.event` | relation | `mainline.event` | yes | table mainline.event |
| `mainline.identity_residue` | relation | `mainline.identity_residue` | yes | table mainline.identity_residue |
| `mainline.ledger_leaf` | relation | `mainline.ledger_leaf` | yes | table mainline.ledger_leaf |
| `mainline.person` | relation | `mainline.person` | yes | table mainline.person |
| `mainline_meas.person_measure_policy` | relation | `mainline_meas.person_measure_policy` | yes | table mainline_meas.person_measure_policy |
| `mainline_meas.recall_policy` | relation | `mainline_meas.recall_policy` | yes | table mainline_meas.recall_policy |
| `policy:mainline.permit` | policy | `mainline.permit` | yes | 7 policy/policies on mainline.permit: fleet_scope, gate_insert, gate_write, hold_blocks_delete, service_read, site_scope, view_owner_read |
| `role:agent_gate` | role | `agent_gate` | yes | role agent_gate |
| `role:agent_recaller` | role | `agent_recaller` | yes | role agent_recaller |
| `role:mainline_auditor` | role | `mainline_auditor` | yes | role mainline_auditor |
| `mainline.coverage_certificate` | relation | `mainline.coverage_certificate` | **no** | relation "mainline.coverage_certificate" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `mainline.discordance_warrant` | relation | `mainline.discordance_warrant` | **no** | relation "mainline.discordance_warrant" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `mainline.frontier_move` | relation | `mainline.frontier_move` | **no** | relation "mainline.frontier_move" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `mainline.merge_conflict` | relation | `mainline.merge_conflict` | **no** | relation "mainline.merge_conflict" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `mainline.observed_assertion` | relation | `mainline.observed_assertion` | **no** | relation "mainline.observed_assertion" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `mainline.propagation` | relation | `mainline.propagation` | **no** | relation "mainline.propagation" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `mainline.recall_run` | relation | `mainline.recall_run` | **no** | relation "mainline.recall_run" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |

---

## The non-passes, grouped by cause

61 non-passing cases resolve to **15 distinct cause(s)**. The grouping is derived from the reason strings with the per-case scope id and external ref masked out — it is not a hand-maintained list — and it is here because *one* wrong column name blocking forty-six cases is one finding reported forty-six times, and a report that did not say so would invite a reader to believe there were forty-six things wrong.

**1. CANNOT RUN, 46 case(s)** — CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

> `CF-02`, `CF-03`, `CF-04`, `CF-05`, `CF-06`, `CF-07`, `CF-08`, `CF-09`, `CF-10`, `CF-11`, `CF-12`, `CF-18`, `CF-19`, `CF-20`, `CF-21`, `CF-22`, `CF-23`, `CF-24`, `CF-25`, `CF-26`, `CF-27`, `CF-28`, `CF-29`, `CF-30`, `CF-31`, `CF-32`, `CF-33`, `CF-34`, `CF-35`, `CF-36`, `CF-37`, `CF-38`, `CF-40`, `CF-41`, `CF-43`, `CF-44`, `CF-45`, `CF-47`, `CF-49`, `CF-52`, `CF-53`, `CF-54`, `CF-56`, `CF-66`, `CF-70`, `CF-71`

**2. CANNOT RUN, 2 case(s)** — CANNOT RUN: mainline.recall_run: relation "mainline.recall_run" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

> `CF-57`, `CF-58`

**3. FAIL, 1 case(s)** — FAIL: expected 23514 gate_closed_when_issued, observed 23502 <no exhibit>. <case>: expected 23514 on 'gate_closed_when_issued'; observed 23502 is outside the modelled taxonomy — a NOT NULL projected column was left unset by a trigger; project the strictest legal value instead (spec/errors.md §1.1, spec rule P-4). Message: null value in column "site_role" violates not-null constraint

> `CF-01`

**4. FAIL, 1 case(s)** — FAIL: expected 23503 fk_check_version, observed P0001 mainline.fn_check_project (exhibit INFERRED from the message, not reported by the driver). <case>: expected 23503 on 'fk_check_version'; observed P0001: gate-class on mainline.fn_check_project. Message: MAINLINE: no blame closure for this clause version — cannot arm a check

> `CF-42`

**5. CANNOT RUN, 1 case(s)** — CANNOT RUN: mainline.merge_conflict: relation "mainline.merge_conflict" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

> `CF-50`

**6. CANNOT RUN, 1 case(s)** — CANNOT RUN: mainline.discordance_warrant: relation "mainline.discordance_warrant" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

> `CF-51`

**7. CANNOT RUN, 1 case(s)** — CANNOT RUN: legal world could not be built at 'commit a policy that has never been anchored' — at or near "_meas": syntax error DETAIL: source SQL: INSERT INTO "mainline"_meas.recall_policy (policy_version, taxonomy_ver, embed_model, gen_model, prompt_version, beam_size, tau, arms, calibration_set_sha256, author_sub, signature) VALUES ('cf59-unanchored', 1, 'titan-v2', 'claude', 'p1', 32, '{"tau0": 5}'::JSONB, '{}'::JSONB, $1, 'conformance', $2) ^ HINT: try \h INSERT. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

> `CF-59`

**8. FAIL, 1 case(s)** — FAIL: expected 23514 no_orphan_controls, observed 00000 <no exhibit>. <case>: the history COMPLETED. Expected 23514 on 'no_orphan_controls'. A gate that admits this write is not a gate.

> `CF-60`

**9. CANNOT RUN, 1 case(s)** — CANNOT RUN: mainline.frontier_move: relation "mainline.frontier_move" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

> `CF-61`

**10. CANNOT RUN, 1 case(s)** — CANNOT RUN: mainline.observed_assertion: relation "mainline.observed_assertion" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

> `CF-62`

**11. FAIL, 1 case(s)** — FAIL: expected 23505 ledger_leaf_pkey, observed 00000 <no exhibit>. <case>: the history COMPLETED. Expected 23505 on 'ledger_leaf_pkey'. A gate that admits this write is not a gate.

> `CF-63`

**12. CANNOT RUN, 1 case(s)** — CANNOT RUN: mainline.propagation: relation "mainline.propagation" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

> `CF-64`

**13. CANNOT RUN, 1 case(s)** — CANNOT RUN: mainline.coverage_certificate: relation "mainline.coverage_certificate" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

> `CF-65`

**14. FAIL, 1 case(s)** — FAIL: expected 23514 witness_quorum, observed 42703 <no exhibit>. SCHEMA NOT MIGRATED — <case>: expected 23514 on 'witness_quorum'; observed 42703 is outside the modelled taxonomy. The object this case needs has not been created yet: this is the expected RED state before the migration that owns the case lands. Message: column "checkpoint_id" does not exist

> `CF-67`

**15. FAIL, 1 case(s)** — FAIL: expected 23514 measure_policy_predates_data, observed 42601 <no exhibit>. <case>: expected 23514 on 'measure_policy_predates_data'; observed 42601 is outside the modelled taxonomy. Message: at or near "_meas": syntax error

> `CF-68`

---

## Every case

| case | status | class | expects | requires | title |
|---|---|---|---|---|---|
| `CF-01` | **FAIL** | gate | `23514` `gate_closed_when_issued` | — | Merge a permit carrying one open blocking check |
| `CF-02` | **CANNOT RUN** | gate | `P0001` `mainline.fn_permit_merge_gate` | — | Merge a permit whose only disposition expired before the merge |
| `CF-03` | **CANNOT RUN** | gate | `P0001` `mainline.fn_permit_merge_gate` | — | Merge a permit whose open_blocking counter was forced to zero out of band |
| `CF-04` | **CANNOT RUN** | gate | `23514` `merge_evidence` | — | Merge a permit with no merged_commit |
| `CF-05` | **CANNOT RUN** | gate | `23514` `reading_floor_when_issued` | — | Merge a permit with an unmet reading floor and no countersignature |
| `CF-06` | **CANNOT RUN** | gate | `P0001` `mainline.fn_permit_merge_gate` | — | Merge a permit citing a clause for which the authority source holds no row |
| `CF-07` | **CANNOT RUN** | gate | `23503` `fk_clearance` | — | A check claiming virulence='routine', severity=1 on a clause whose closure holds max_severity=5, then a mechanism_absent disposition against it |
| `CF-08` | **CANNOT RUN** | gate | `P0001` `mainline.fn_refuse_mutation` | — | Rewrite the blame closure: as an UPDATE, then as a new generation with a lowered severity |
| `CF-09` | **CANNOT RUN** | gate | `23505` `merge_record_pkey` | — | Merge the same subject twice |
| `CF-10` | **CANNOT RUN** | gate | `P0001` `mainline.fn_check_materialised` | — | Materialise a blocking check against an already-merged permit |
| `CF-11` | **CANNOT RUN** | admit | `00000` `blocking_check_dedupe_key_key` | — | Materialise the same weaken_over_blood check twice with precursor_event_id NULL |
| `CF-12` | **CANNOT RUN** | gate | `23505` `one_live_disposition` | — | Two live dispositions against one blocking check |
| `CF-13` | **PASS** | gate | `23503` `legal_edge` | — | Transition a permit straight from draft to merged |
| `CF-14` | **PASS** | gate | `23505` `linear` | — | Two permit_event rows appended from the same head |
| `CF-15` | **PASS** | gate | `23505` `cr_linear` | — | Two cr_event rows appended from the same head |
| `CF-16` | **PASS** | gate | `P0001` `mainline.fn_permit_event_chain` | — | Append a permit_event whose prev_digest does not match the predecessor's chain_digest |
| `CF-17` | **PASS** | gate | `P0001` `mainline.fn_permit_event_chain` | — | Append a permit_event declaring a prev_seq with no predecessor row |
| `CF-18` | **CANNOT RUN** | gate | `23503` `fk_exposure` | — | Disposition against a (receipt, check) pair that was never materialised to the signing actor |
| `CF-19` | **CANNOT RUN** | gate | `23514` `rank_floor` | — | Sign with a client-supplied signer_rank of 6 on a person whose live rank is 2 |
| `CF-20` | **CANNOT RUN** | gate | `P0001` `mainline.fn_disposition_project` | — | Disposition signed by a subject with no person row |
| `CF-21` | **CANNOT RUN** | gate | `P0001` `mainline.fn_disposition_project` | — | Disposition against an exposure receipt that has already expired |
| `CF-22` | **CANNOT RUN** | admit | `00000` `gate_write` | `policy:mainline.permit` | Run the entire gate transaction with FORCE ROW LEVEL SECURITY active, then drop the write policy |
| `CF-23` | **CANNOT RUN** | gate | `23503` `fk_clearance` | — | accept_residual disposition at virulence blood_major |
| `CF-24` | **CANNOT RUN** | gate | `23514` `substantive` | — | Disposition with a rationale shorter than the substantive floor |
| `CF-25` | **CANNOT RUN** | gate | `23514` `uv_required` | — | Disposition recorded with user_verified = false |
| `CF-26` | **CANNOT RUN** | gate | `23514` `distinct_credential` | — | Countersignature made with the signer's own credential |
| `CF-27` | **CANNOT RUN** | gate | `23514` `needs_second_signer` | — | Clearance kind requiring a second signer, supplied without one |
| `CF-28` | **CANNOT RUN** | gate | `23514` `needs_foreign_org` | — | Clearance kind requiring a foreign-org countersigner, countersigned inside the same org |
| `CF-29` | **CANNOT RUN** | gate | `23514` `needs_compensating` | — | Clearance kind requiring a compensating control, supplied without one |
| `CF-30` | **CANNOT RUN** | gate | `23514` `needs_predicate` | — | mechanism_absent disposition with no bounded machine-checkable predicate |
| `CF-31` | **CANNOT RUN** | gate | `23514` `cr_gate_closed_when_merged` | — | Merge a change_request carrying an undispositioned weaken_over_blood check |
| `CF-32` | **CANNOT RUN** | gate | `23514` `needs_reassert` | — | Clearance kind requiring reassertion, supplied with no reassert_by |
| `CF-33` | **CANNOT RUN** | gate | `23514` `ttl_enforced` | — | Disposition whose expires_at exceeds signed_at plus the clearance's max_ttl_hours |
| `CF-34` | **CANNOT RUN** | gate | `23514` `override_escalates` | — | Emergency override signed at a rank below 3 + prior_override_count |
| `CF-35` | **CANNOT RUN** | gate | `23514` `waiver_authority` | `mainline.person` | Waiver at blood_fatal by a signer whose frozen competency snapshot lacks the isolation authorisation |
| `CF-36` | **CANNOT RUN** | gate | `23514` `verbatim_floor` | — | mechanism_absent disposition citing only gist evidence |
| `CF-37` | **CANNOT RUN** | gate | `23514` `verbatim_needs_anchor` | — | Verbatim citation with no object key and no span digest |
| `CF-38` | **CANNOT RUN** | gate | `P0001` `mainline.fn_disposition_retract_only` | — | UPDATE a disposition column other than retracted_by |
| `CF-39` | **PASS** | gate | `P0001` `mainline.fn_refuse_mutation` | — | UPDATE and DELETE against an append-only obligation table |
| `CF-40` | **CANNOT RUN** | gate | `23503` `epoch_pin_permit` | — | Retract a disposition after the permit has merged |
| `CF-41` | **CANNOT RUN** | gate | `23514` `exactly_one_subject` | — | Blocking check naming both a permit and a change request |
| `CF-42` | **FAIL** | gate | `23503` `fk_check_version` | — | Blocking check against a clause version that does not exist |
| `CF-43` | **CANNOT RUN** | retry | `40001` `mainline.permit.open_blocking` | — | Materialise an obligation concurrently with the merge of the same permit |
| `CF-44` | **CANNOT RUN** | gate | `23505` `merge_record_pkey` | — | N parallel merges of one permit yield exactly one merge record |
| `CF-45` | **CANNOT RUN** | gate | `23514` `gate_closed_when_issued` | — | Run the entire gate history at READ COMMITTED |
| `CF-46` | **PASS** | admit | `00000` `mainline.permit_event.chain_digest` | — | Reconstruct the subject's state at a past instant from the event chain, and prove AS OF SYSTEM TIME cannot reach it |
| `CF-47` | **CANNOT RUN** | deny | `42501` `grant:INSERT:mainline.blocking_check:agent_recaller` | `role:agent_recaller` | The recall role attempts to insert a blocking check |
| `CF-48` | **PASS** | deny | `42501` `grant:DDL:mainline.permit:agent_gate` | `role:agent_gate` | The application role attempts to drop the merge-gate trigger |
| `CF-49` | **CANNOT RUN** | gate | `23514` `identity_conserved_when_issued` | `mainline.identity_residue` | Merge a permit carrying un-dispositioned identity residue |
| `CF-50` | **CANNOT RUN** | gate | `23514` `conflicts_resolved_when_issued` | `mainline.merge_conflict` | Merge a permit carrying an open fleet conflict |
| `CF-51` | **CANNOT RUN** | gate | `23514` `no_open_warrant_when_issued` | `mainline.discordance_warrant` | Merge a permit citing a clause under an open discordance warrant |
| `CF-52` | **CANNOT RUN** | gate | `23514` `boundary_certified_when_issued` | `mainline.boundary_certificate` | Merge a permit whose boundary certificate reports unmodelled or under-declared assets |
| `CF-53` | **CANNOT RUN** | gate | `P0001` `mainline.fn_permit_merge_gate` | `mainline.boundary_certificate` | Merge a permit with no boundary certificate at all |
| `CF-54` | **CANNOT RUN** | gate | `23514` `inference_never_blocks` | `mainline.blame_edge` | A semantically inferred blame edge marked active |
| `CF-55` | **PASS** | gate | `23514` `model_cannot_arm` | `mainline.event` | A model-rated severity used to arm the gate |
| `CF-56` | **CANNOT RUN** | gate | `P0001` `mainline.fn_clause_version_guard` | `mainline.clause_version` | A clause version whose sev_max is lower than its parent's |
| `CF-57` | **CANNOT RUN** | gate | `23514` `bonded_fatalities_all_blocking` | `mainline.recall_run` | A severity-5 event bonded to the permit's activity node, materialised as advisory |
| `CF-58` | **CANNOT RUN** | gate | `23514` `candidates_conserved` | `mainline.recall_run` | A recall run whose candidate set is not exactly partitioned into blocking, advisory, silenced and deduped |
| `CF-59` | **CANNOT RUN** | gate | `P0001` `mainline.fn_recall_policy_anchored` | `mainline_meas.recall_policy` | A recall run under a policy version whose anchoring is absent or outside a cosigned checkpoint |
| `CF-60` | **FAIL** | gate | `23514` `no_orphan_controls` | `mainline.carriage` | Supersede a document that still carries a live control series |
| `CF-61` | **CANNOT RUN** | gate | `23514` `frontier_evidence` | `mainline.frontier_move` | A weakening below the risk frontier citing evidence that predates the frontier move |
| `CF-62` | **CANNOT RUN** | gate | `23514` `undetermined_never_blocks` | `mainline.observed_assertion` | An UNDETERMINED fixity result used to block |
| `CF-63` | **FAIL** | gate | `23505` `ledger_leaf_pkey` | `mainline.ledger_leaf` | Write two ledger leaves at the same sequence position |
| `CF-64` | **CANNOT RUN** | gate | `23514` `only_tightenings_travel` | `mainline.propagation` | Propagate a weakening across the fleet |
| `CF-65` | **CANNOT RUN** | gate | `23514` `empty_result_certified` | `mainline.coverage_certificate` | Record an empty retrieval result with no coverage certificate bound to the index generation |
| `CF-66` | **CANNOT RUN** | gate | `23514` `carried_bounded` | `mainline.carried_disposition` | A carried disposition whose expiry exceeds its declared window |
| `CF-67` | **FAIL** | gate | `23514` `witness_quorum` | `mainline.cosignature` | Mark a checkpoint admissible with cosignatures from fewer than k trust domains, or with none adverse |
| `CF-68` | **FAIL** | gate | `23514` `measure_policy_predates_data` | `mainline_meas.person_measure_policy` | Compute a standing measurement over data predating the customer-signed measurement policy |
| `CF-69` | **PASS** | deny | `42501` `grant:INSERT:mainline.disposition:mainline_auditor` | `role:mainline_auditor` | The audit identity attempts to write outside its single permitted attestation table |
| `CF-70` | **CANNOT RUN** | gate | `23514` `gate_closed_when_issued` | — | A permit refused with three obligations of which two are already dispositioned emits a MUS naming exactly the third |
| `CF-71` | **CANNOT RUN** | gate | `23503` `fk_clearance` | — | A clearance-lattice refusal names exactly the verdict kinds that DO exist at that virulence |

---

## PASS — 10 case(s)

*the database refused exactly as the manifest says it must.*

### `CF-13` — Transition a permit straight from draft to merged

- **class** `gate` · **expects** `23503` on `legal_edge` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `aebda58f-3c32-58c0-b76a-04bae666c22a`
- **observed** refused 23503 on legal_edge. CF-13: 23503 on legal_edge at step ''

### `CF-14` — Two permit_event rows appended from the same head

- **class** `gate` · **expects** `23505` on `linear` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `b0d33418-0bd0-5ab8-beae-7af42ac29582`
- **observed** refused 23505 on linear. CF-14: 23505 on linear at step ''

### `CF-15` — Two cr_event rows appended from the same head

- **class** `gate` · **expects** `23505` on `cr_linear` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `4aeee3b2-4feb-55fd-85dd-3b910c00df9e`
- **observed** refused 23505 on cr_linear. CF-15: 23505 on cr_linear at step ''

### `CF-16` — Append a permit_event whose prev_digest does not match the predecessor's chain_digest

- **class** `gate` · **expects** `P0001` on `mainline.fn_permit_event_chain` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `a5faef6a-aa21-5ced-aa82-7ac4fff134c4`
- **observed** refused P0001 on mainline.fn_permit_event_chain. CF-16: P0001 on mainline.fn_permit_event_chain (exhibit inferred) at step ''

### `CF-17` — Append a permit_event declaring a prev_seq with no predecessor row

- **class** `gate` · **expects** `P0001` on `mainline.fn_permit_event_chain` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `b0dbb8fc-4136-5968-8c55-473de4e9a000`
- **observed** refused P0001 on mainline.fn_permit_event_chain. CF-17: P0001 on mainline.fn_permit_event_chain (exhibit inferred) at step ''

### `CF-39` — UPDATE and DELETE against an append-only obligation table

- **class** `gate` · **expects** `P0001` on `mainline.fn_refuse_mutation` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `b35c0214-17da-5e69-91e9-5d4300e35b5f`
- **observed** refused P0001 on mainline.fn_refuse_mutation. CF-39: P0001 on mainline.fn_refuse_mutation (exhibit inferred) at step ''

### `CF-46` — Reconstruct the subject's state at a past instant from the event chain, and prove AS OF SYSTEM TIME cannot reach it

- **class** `admit` · **expects** `00000` on `mainline.permit_event.chain_digest` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `f81eaacb-685a-52ee-b773-30c414bc5aa5`
- **observed** CF-46: completed (00000)

### `CF-48` — The application role attempts to drop the merge-gate trigger

- **class** `deny` · **expects** `42501` on `grant:DDL:mainline.permit:agent_gate` · **refusal depth ≥** 1 · **milestone** `K1`
- **requires** `role:agent_gate`
- **site_id** `0846201a-afed-5271-b4fb-3bbc6430b3e4`
- **observed** refused 42501 on grant:DDL:mainline.permit:agent_gate. CF-48: 42501 on grant:DDL:mainline.permit:agent_gate (exhibit inferred) at step ''

### `CF-55` — A model-rated severity used to arm the gate

- **class** `gate` · **expects** `23514` on `model_cannot_arm` · **refusal depth ≥** 1 · **milestone** `K3`
- **requires** `mainline.event`
- **site_id** `09f7c060-925f-5643-a0d5-d225d27d4165`
- **observed** refused 23514 on model_cannot_arm. CF-55: 23514 on model_cannot_arm at step ''

### `CF-69` — The audit identity attempts to write outside its single permitted attestation table

- **class** `deny` · **expects** `42501` on `grant:INSERT:mainline.disposition:mainline_auditor` · **refusal depth ≥** 1 · **milestone** `K6`
- **requires** `role:mainline_auditor`
- **site_id** `9553d324-dfee-55a9-aa79-e6cf362ff05e`
- **observed** refused 42501 on grant:INSERT:mainline.disposition:mainline_auditor. CF-69: 42501 on grant:INSERT:mainline.disposition:mainline_auditor (exhibit inferred) at step ''

---

## FAIL — 6 case(s)

*it did not — including a relation reported absent, named here.*

### `CF-01` — Merge a permit carrying one open blocking check

- **class** `gate` · **expects** `23514` on `gate_closed_when_issued` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `65361d1a-79dc-50f0-8555-b3e1502c72aa`

> FAIL: expected 23514 gate_closed_when_issued, observed 23502 <no exhibit>. CF-01: expected 23514 on 'gate_closed_when_issued'; observed 23502 is outside the modelled taxonomy — a NOT NULL projected column was left unset by a trigger; project the strictest legal value instead (spec/errors.md §1.1, spec rule P-4). Message: null value in column "site_role" violates not-null constraint

### `CF-42` — Blocking check against a clause version that does not exist

- **class** `gate` · **expects** `23503` on `fk_check_version` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `9d2dfcc1-42e6-5fc5-9ff2-1dd519f7d290`

> FAIL: expected 23503 fk_check_version, observed P0001 mainline.fn_check_project (exhibit INFERRED from the message, not reported by the driver). CF-42: expected 23503 on 'fk_check_version'; observed P0001: gate-class on mainline.fn_check_project. Message: MAINLINE: no blame closure for this clause version — cannot arm a check

### `CF-60` — Supersede a document that still carries a live control series

- **class** `gate` · **expects** `23514` on `no_orphan_controls` · **refusal depth ≥** 1 · **milestone** `K3`
- **requires** `mainline.carriage`
- **site_id** `a3de5aec-5bc8-50a7-8248-6885f08a5011`

> FAIL: expected 23514 no_orphan_controls, observed 00000 <no exhibit>. CF-60: the history COMPLETED. Expected 23514 on 'no_orphan_controls'. A gate that admits this write is not a gate.

### `CF-63` — Write two ledger leaves at the same sequence position

- **class** `gate` · **expects** `23505` on `ledger_leaf_pkey` · **refusal depth ≥** 1 · **milestone** `K2`
- **requires** `mainline.ledger_leaf`
- **site_id** `d00ed3df-167c-5465-a72b-5d15ab08e01a`

> FAIL: expected 23505 ledger_leaf_pkey, observed 00000 <no exhibit>. CF-63: the history COMPLETED. Expected 23505 on 'ledger_leaf_pkey'. A gate that admits this write is not a gate.

### `CF-67` — Mark a checkpoint admissible with cosignatures from fewer than k trust domains, or with none adverse

- **class** `gate` · **expects** `23514` on `witness_quorum` · **refusal depth ≥** 1 · **milestone** `K9`
- **requires** `mainline.cosignature`
- **site_id** `041960ef-7f7a-5aa7-af1b-a6ebbf400d01`

> FAIL: expected 23514 witness_quorum, observed 42703 <no exhibit>. SCHEMA NOT MIGRATED — CF-67: expected 23514 on 'witness_quorum'; observed 42703 is outside the modelled taxonomy. The object this case needs has not been created yet: this is the expected RED state before the migration that owns the case lands. Message: column "checkpoint_id" does not exist

### `CF-68` — Compute a standing measurement over data predating the customer-signed measurement policy

- **class** `gate` · **expects** `23514` on `measure_policy_predates_data` · **refusal depth ≥** 1 · **milestone** `K8`
- **requires** `mainline_meas.person_measure_policy`
- **site_id** `981f9f13-4d31-5197-b62b-444d352e735c`

> FAIL: expected 23514 measure_policy_predates_data, observed 42601 <no exhibit>. CF-68: expected 23514 on 'measure_policy_predates_data'; observed 42601 is outside the modelled taxonomy. Message: at or near "_meas": syntax error

---

## CANNOT RUN — 55 case(s)

*nothing was asked of the gate: the legal world would not build, or a declared capability was measured absent.*

### `CF-02` — Merge a permit whose only disposition expired before the merge

- **class** `gate` · **expects** `P0001` on `mainline.fn_permit_merge_gate` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `653c2137-e398-5fa1-86c3-9781a8a4b4e8`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-03` — Merge a permit whose open_blocking counter was forced to zero out of band

- **class** `gate` · **expects** `P0001` on `mainline.fn_permit_merge_gate` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `63bc48e1-16ed-5f9a-907a-73123261071f`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-04` — Merge a permit with no merged_commit

- **class** `gate` · **expects** `23514` on `merge_evidence` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `38413307-df86-5e30-94eb-f877586c3a5b`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-05` — Merge a permit with an unmet reading floor and no countersignature

- **class** `gate` · **expects** `23514` on `reading_floor_when_issued` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `16c77e76-863d-5042-b3c8-fa1831ccbdaa`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-06` — Merge a permit citing a clause for which the authority source holds no row

- **class** `gate` · **expects** `P0001` on `mainline.fn_permit_merge_gate` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `f1295012-ae01-516f-8606-db1b4298ba9a`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-07` — A check claiming virulence='routine', severity=1 on a clause whose closure holds max_severity=5, then a mechanism_absent disposition against it

- **class** `gate` · **expects** `23503` on `fk_clearance` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `89fdf56a-c79b-5094-b91c-b5441955c84a`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-08` — Rewrite the blame closure: as an UPDATE, then as a new generation with a lowered severity

- **class** `gate` · **expects** `P0001` on `mainline.fn_refuse_mutation` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `3816dd73-16dc-59ed-aa95-f456c0c6a4b6`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-09` — Merge the same subject twice

- **class** `gate` · **expects** `23505` on `merge_record_pkey` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `e7f5eda4-c6a8-5406-b4c6-32d67b41f77c`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-10` — Materialise a blocking check against an already-merged permit

- **class** `gate` · **expects** `P0001` on `mainline.fn_check_materialised` · **refusal depth ≥** 3 · **milestone** `K1`
- **site_id** `cc761548-28d3-5ec3-9cab-b268bf685d13`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-11` — Materialise the same weaken_over_blood check twice with precursor_event_id NULL

- **class** `admit` · **expects** `00000` on `blocking_check_dedupe_key_key` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `f17d4c50-f3b0-54cb-a946-48532b9bb26a`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-12` — Two live dispositions against one blocking check

- **class** `gate` · **expects** `23505` on `one_live_disposition` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `f46b0d05-e90c-5525-8d45-ea6f07ea2777`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-18` — Disposition against a (receipt, check) pair that was never materialised to the signing actor

- **class** `gate` · **expects** `23503` on `fk_exposure` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `89e1a5b3-a9b8-5862-a530-dce8fddbfed3`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-19` — Sign with a client-supplied signer_rank of 6 on a person whose live rank is 2

- **class** `gate` · **expects** `23514` on `rank_floor` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `83310022-d854-5a5a-9bab-96ab70bc0913`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-20` — Disposition signed by a subject with no person row

- **class** `gate` · **expects** `P0001` on `mainline.fn_disposition_project` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `a496241f-15d5-58bc-84da-2d595f9af3c4`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-21` — Disposition against an exposure receipt that has already expired

- **class** `gate` · **expects** `P0001` on `mainline.fn_disposition_project` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `1f2785c3-4333-5cdc-887b-d009ee390b64`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-22` — Run the entire gate transaction with FORCE ROW LEVEL SECURITY active, then drop the write policy

- **class** `admit` · **expects** `00000` on `gate_write` · **refusal depth ≥** 1 · **milestone** `K1`
- **requires** `policy:mainline.permit`
- **site_id** `cd427e30-1ccb-5d36-8bf4-2c72c4ee5854`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-23` — accept_residual disposition at virulence blood_major

- **class** `gate` · **expects** `23503` on `fk_clearance` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `ad4d3d77-6b03-5667-a012-9923ae69a6d0`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-24` — Disposition with a rationale shorter than the substantive floor

- **class** `gate` · **expects** `23514` on `substantive` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `0ca4f977-daa2-5214-9e34-a145f0aaa320`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-25` — Disposition recorded with user_verified = false

- **class** `gate` · **expects** `23514` on `uv_required` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `d3e92dca-7abd-5473-94e0-4fcfd9b3fa80`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-26` — Countersignature made with the signer's own credential

- **class** `gate` · **expects** `23514` on `distinct_credential` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `835bc46e-0d20-53a8-867d-86ca8f6d3920`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-27` — Clearance kind requiring a second signer, supplied without one

- **class** `gate` · **expects** `23514` on `needs_second_signer` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `f81e731c-1809-59dd-8375-1f23f6c5ff84`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-28` — Clearance kind requiring a foreign-org countersigner, countersigned inside the same org

- **class** `gate` · **expects** `23514` on `needs_foreign_org` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `ae305c23-014a-54f5-8a41-f9df6430c345`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-29` — Clearance kind requiring a compensating control, supplied without one

- **class** `gate` · **expects** `23514` on `needs_compensating` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `17758d51-e4e4-5ae8-9d0c-4e202a46a257`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-30` — mechanism_absent disposition with no bounded machine-checkable predicate

- **class** `gate` · **expects** `23514` on `needs_predicate` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `2aaf44e3-1e7d-593a-b99b-2c540ebac48b`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-31` — Merge a change_request carrying an undispositioned weaken_over_blood check

- **class** `gate` · **expects** `23514` on `cr_gate_closed_when_merged` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `9a9e820c-1087-5f59-a779-7f35a5e1e597`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-32` — Clearance kind requiring reassertion, supplied with no reassert_by

- **class** `gate` · **expects** `23514` on `needs_reassert` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `ecc72acd-1d22-5282-845e-199507fae30f`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-33` — Disposition whose expires_at exceeds signed_at plus the clearance's max_ttl_hours

- **class** `gate` · **expects** `23514` on `ttl_enforced` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `386a723e-e20e-5a14-adaf-03978bd9664d`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-34` — Emergency override signed at a rank below 3 + prior_override_count

- **class** `gate` · **expects** `23514` on `override_escalates` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `a88723fe-c312-50e8-a665-2fd81a522727`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-35` — Waiver at blood_fatal by a signer whose frozen competency snapshot lacks the isolation authorisation

- **class** `gate` · **expects** `23514` on `waiver_authority` · **refusal depth ≥** 1 · **milestone** `K5`
- **requires** `mainline.person`
- **site_id** `c1d68638-7969-50d1-b3a3-784b50730eed`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-36` — mechanism_absent disposition citing only gist evidence

- **class** `gate` · **expects** `23514` on `verbatim_floor` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `63e45ee3-24e2-504f-ba49-6c1d1441bbf7`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-37` — Verbatim citation with no object key and no span digest

- **class** `gate` · **expects** `23514` on `verbatim_needs_anchor` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `a593b8ae-7a02-5c97-8568-04a7db9187e3`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-38` — UPDATE a disposition column other than retracted_by

- **class** `gate` · **expects** `P0001` on `mainline.fn_disposition_retract_only` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `44473949-93ae-54df-99a7-545113ee8893`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-40` — Retract a disposition after the permit has merged

- **class** `gate` · **expects** `23503` on `epoch_pin_permit` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `f7bfa468-765b-56c4-84aa-993acca81f3b`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-41` — Blocking check naming both a permit and a change request

- **class** `gate` · **expects** `23514` on `exactly_one_subject` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `b0fddcca-afd1-57f3-976d-1d0c4902fd56`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-43` — Materialise an obligation concurrently with the merge of the same permit

- **class** `retry` · **expects** `40001` on `mainline.permit.open_blocking` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `ecb6f055-a8f2-5cd4-b6be-07b6478c0f75`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-44` — N parallel merges of one permit yield exactly one merge record

- **class** `gate` · **expects** `23505` on `merge_record_pkey` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `49ab372b-5296-5c9b-ad16-e8241b8d277d`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-45` — Run the entire gate history at READ COMMITTED

- **class** `gate` · **expects** `23514` on `gate_closed_when_issued` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `e1ad4151-f8cd-5a2e-b28c-ab5640c8e6b3`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-47` — The recall role attempts to insert a blocking check

- **class** `deny` · **expects** `42501` on `grant:INSERT:mainline.blocking_check:agent_recaller` · **refusal depth ≥** 1 · **milestone** `K1`
- **requires** `role:agent_recaller`
- **site_id** `17b246cf-c29e-5b76-963e-8f7fef5d2a60`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-49` — Merge a permit carrying un-dispositioned identity residue

- **class** `gate` · **expects** `23514` on `identity_conserved_when_issued` · **refusal depth ≥** 2 · **milestone** `K3`
- **requires** `mainline.identity_residue`
- **site_id** `ef237ea8-ad91-56c7-9dac-dc357d855954`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-50` — Merge a permit carrying an open fleet conflict

- **class** `gate` · **expects** `23514` on `conflicts_resolved_when_issued` · **refusal depth ≥** 2 · **milestone** `K7`
- **requires** `mainline.merge_conflict`
- **site_id** `1fb7b0cf-882d-54eb-81c9-c90fa6016459`

> CANNOT RUN: mainline.merge_conflict: relation "mainline.merge_conflict" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

### `CF-51` — Merge a permit citing a clause under an open discordance warrant

- **class** `gate` · **expects** `23514` on `no_open_warrant_when_issued` · **refusal depth ≥** 2 · **milestone** `K7`
- **requires** `mainline.discordance_warrant`
- **site_id** `fd0c1093-a567-511a-aedf-03b8a6f97fca`

> CANNOT RUN: mainline.discordance_warrant: relation "mainline.discordance_warrant" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

### `CF-52` — Merge a permit whose boundary certificate reports unmodelled or under-declared assets

- **class** `gate` · **expects** `23514` on `boundary_certified_when_issued` · **refusal depth ≥** 2 · **milestone** `K5`
- **requires** `mainline.boundary_certificate`
- **site_id** `98e1fea1-5be0-5410-b83e-f5f1d3af33ed`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-53` — Merge a permit with no boundary certificate at all

- **class** `gate` · **expects** `P0001` on `mainline.fn_permit_merge_gate` · **refusal depth ≥** 2 · **milestone** `K5`
- **requires** `mainline.boundary_certificate`
- **site_id** `adff34f9-0d62-52cd-aab6-84f18fdc54d5`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-54` — A semantically inferred blame edge marked active

- **class** `gate` · **expects** `23514` on `inference_never_blocks` · **refusal depth ≥** 1 · **milestone** `K3`
- **requires** `mainline.blame_edge`
- **site_id** `354888b8-8258-55e5-9fad-161c96c68a96`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-56` — A clause version whose sev_max is lower than its parent's

- **class** `gate` · **expects** `P0001` on `mainline.fn_clause_version_guard` · **refusal depth ≥** 1 · **milestone** `K3`
- **requires** `mainline.clause_version`
- **site_id** `9f50a35a-c94b-51ee-b6db-44e264847458`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-57` — A severity-5 event bonded to the permit's activity node, materialised as advisory

- **class** `gate` · **expects** `23514` on `bonded_fatalities_all_blocking` · **refusal depth ≥** 1 · **milestone** `K4`
- **requires** `mainline.recall_run`
- **site_id** `fa03e765-57db-5048-9fef-76473d46bbe6`

> CANNOT RUN: mainline.recall_run: relation "mainline.recall_run" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

### `CF-58` — A recall run whose candidate set is not exactly partitioned into blocking, advisory, silenced and deduped

- **class** `gate` · **expects** `23514` on `candidates_conserved` · **refusal depth ≥** 1 · **milestone** `K4`
- **requires** `mainline.recall_run`
- **site_id** `e8d9e9c6-d519-5d26-96dd-fd0251b3854b`

> CANNOT RUN: mainline.recall_run: relation "mainline.recall_run" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

### `CF-59` — A recall run under a policy version whose anchoring is absent or outside a cosigned checkpoint

- **class** `gate` · **expects** `P0001` on `mainline.fn_recall_policy_anchored` · **refusal depth ≥** 1 · **milestone** `K4`
- **requires** `mainline_meas.recall_policy`
- **site_id** `89c62984-a4a9-5f34-92cb-3013824e82ad`

> CANNOT RUN: legal world could not be built at 'commit a policy that has never been anchored' — at or near "_meas": syntax error DETAIL: source SQL: INSERT INTO "mainline"_meas.recall_policy (policy_version, taxonomy_ver, embed_model, gen_model, prompt_version, beam_size, tau, arms, calibration_set_sha256, author_sub, signature) VALUES ('cf59-unanchored', 1, 'titan-v2', 'claude', 'p1', 32, '{"tau0": 5}'::JSONB, '{}'::JSONB, $1, 'conformance', $2) ^ HINT: try \h INSERT. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-61` — A weakening below the risk frontier citing evidence that predates the frontier move

- **class** `gate` · **expects** `23514` on `frontier_evidence` · **refusal depth ≥** 2 · **milestone** `K7`
- **requires** `mainline.frontier_move`
- **site_id** `d5f7b349-00a5-58de-ad01-bda79fc41274`

> CANNOT RUN: mainline.frontier_move: relation "mainline.frontier_move" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

### `CF-62` — An UNDETERMINED fixity result used to block

- **class** `gate` · **expects** `23514` on `undetermined_never_blocks` · **refusal depth ≥** 1 · **milestone** `K7`
- **requires** `mainline.observed_assertion`
- **site_id** `ae807f67-b5e4-57ad-aff2-1c5fdc87279f`

> CANNOT RUN: mainline.observed_assertion: relation "mainline.observed_assertion" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

### `CF-64` — Propagate a weakening across the fleet

- **class** `gate` · **expects** `23514` on `only_tightenings_travel` · **refusal depth ≥** 1 · **milestone** `K7`
- **requires** `mainline.propagation`
- **site_id** `7dc6294e-5777-5b3d-93ac-65f5354ad699`

> CANNOT RUN: mainline.propagation: relation "mainline.propagation" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

### `CF-65` — Record an empty retrieval result with no coverage certificate bound to the index generation

- **class** `gate` · **expects** `23514` on `empty_result_certified` · **refusal depth ≥** 1 · **milestone** `K4`
- **requires** `mainline.coverage_certificate`
- **site_id** `5adc8dfa-13e1-5f72-8744-46fcacdfcb6c`

> CANNOT RUN: mainline.coverage_certificate: relation "mainline.coverage_certificate" does not exist (pg_class; schema "mainline" is present in database "prod_w9")

### `CF-66` — A carried disposition whose expiry exceeds its declared window

- **class** `gate` · **expects** `23514` on `carried_bounded` · **refusal depth ≥** 1 · **milestone** `K5`
- **requires** `mainline.carried_disposition`
- **site_id** `df444fdd-d63b-5748-84b0-ee4b9c9e372d`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-70` — A permit refused with three obligations of which two are already dispositioned emits a MUS naming exactly the third

- **class** `gate` · **expects** `23514` on `gate_closed_when_issued` · **refusal depth ≥** 2 · **milestone** `K1`
- **site_id** `9cc1effc-0b1a-532f-94fb-da38237d35e0`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

### `CF-71` — A clearance-lattice refusal names exactly the verdict kinds that DO exist at that virulence

- **class** `gate` · **expects** `23503` on `fk_clearance` · **refusal depth ≥** 1 · **milestone** `K1`
- **site_id** `0c939155-aa0d-587a-a6e5-4107dabbfd89`

> CANNOT RUN: legal world could not be built at 'clause_version' — column "body_sha256" does not exist. Nothing was asked of the gate, so this is not a red gate: it is a setup statement the database refused.

---

## How this was produced

- **database built by** scripts/chain/apply_chain.py
- **census script** `scripts/qa/run_conformance_census.py` (`scripts/qa/run_conformance_census.py --build --run-id cert-final`)
- **no case implementation, no manifest entry and no `--requires` declaration was touched to produce this document.** The suite was run with `--autodetect-requires` so that an unmet capability is measured and named rather than asserted.
- **machine-readable twin** [`qa/conformance-census.json`](../../qa/conformance-census.json)

Re-run: `just conform-census`, or `scripts/qa/run_conformance_census.py --build --run-id cert-final`.
