# ALGORITHMS — domain implementation plan

**Lead:** Algorithms (our own algorithms). **Date:** 2026-08-04. **Authority:** `ARCHITECTURE.md` §3, §5.3, §5.4, §5.5, §5.11, §6, §16, §18; `BUILD_PLAN.md` K3/K4/K8; `research/05-architecture/clause-identity.md`.
This document decides HOW the domain is built. Where the two authoritative documents already decided, this document implements — it does not re-litigate.

---

## 0. What this domain owns, in one sentence

The domain owns **the arithmetic that decides whether an edit to a safety control is a weakening, and whether a blood-written obligation survived an edit at all** — and it owns making both of those facts *things the database refuses to be wrong about*, rather than model outputs that a gate happens to read.

The originality claim in this domain rests on one asymmetry and one recursion:

- **Asymmetry (Conservation of Blame Mass).** Every ancestor clause carrying a blame edge to a `severity ≥ 4` event is, in commit `c`, one of exactly three things: *matched*, *matched through a recorded split/merge*, or *explicitly absent with a signed disposition*. There is no fourth state. Evading the matcher therefore produces an **orphaned blood-written obligation** — which is a louder gate than the weakening it was hiding. Matcher recall failure converts into an adjudicable false **positive** instead of a silent false negative. This inversion is only real if the accounting is *arithmetic enforced by the database*, which is why §5 of this plan turns CBM from a narrative into a `CHECK`.
- **Recursion (DIRECTRIX).** `safe_direction(parameter)` — the registry that decides which way a setpoint move is dangerous — is stored **as clauses in the gated commit DAG, with its own blame edges**. Editing the gate's own parameter table is therefore a `change_request` that the gate refuses to merge on the same terms as any other weakening. The gate's parameters are gated by the gate.

---

## 1. Decisions made here (each with its one-line justification)

| # | Decision | Justification |
|---|---|---|
| D1 | **`mainline_domain` never imports a model SDK.** Path B (LLM) lives in a physically separate package `mainline-delta-oracle`; the domain holds only a `Protocol` and a pure resolution function over an `OracleVerdict` dataclass | P7: no component that can decide a state transition may reach a model — and the lattice *does* decide a state transition |
| D2 | **`cat_key` preimage is a length-prefixed typed field encoding, not JSON** | Removes a second vendored RFC 8785 canonicaliser from the repo and makes the preimage byte-exact and trivially re-implementable by an opposing expert; golden vectors ship as a fixture |
| D3 | **MinHash is hand-rolled** (one blake2b-64 base hash per shingle + 128 committed affine permutations mod 2⁶¹−1), no `datasketch` | Determinism across interpreter versions is an evidentiary requirement; `hash()` is salted, `datasketch` seeds are an unpinned dependency, and the permutation table becomes a versioned, committed artefact (`minhash_version`) |
| D4 | **The assignment stage never breaks a tie.** Degeneracy in the LAP optimum is *detected* and emitted as `identity_residue.reason='ambiguous'` | A tie-break is an unrecorded decision by a solver; a blocking row is a recorded decision by a human. Also removes the SciPy-degeneracy reproducibility problem entirely rather than papering it |
| D5 | **Gauge↔absolute pressure conversion raises, always** | `50 psig → 344.7 kPa_g` is safe; `50 psig → 446 kPa(a)` silently flips a `safe_direction` comparison. A vendored Pint definition file plus a `reference` field on every `Quantity` makes the mistake unrepresentable |
| D6 | **Unknown parameter ⇒ abstain ⇒ `weaken`.** A setpoint change on a parameter absent from DIRECTRIX at `as_of_commit` is not "neutral" | P3 fail-closed. It also gives the registry an adoption ratchet: the way to stop over-blocking is to ratify the parameter, which is a signed commit |
| D7 | **`control_delta` of record = the more forceful of `delta(parent→new)` and `delta(blame_origin→new)`** | Salami defence falls out of diachronic gating at zero cost (research §5); computing the origin delta *directly* from CATs avoids needing a composition algebra over labels |
| D8 | **Every `weaken`/`remove` with `delta_basis='lattice'` must carry `delta_witness` rows written earlier in the same transaction, or the version insert is refused** | I14 minimal-unsatisfiable-subset becomes a write precondition rather than a rendering concern; an unexplainable weaken verdict cannot exist |
| D9 | ~~**Algorithm-domain SQL occupies migration band `0200–0219` only.** `0001–0171` belong to the schema/kernel lead~~ **REVOKED 2026-08-08.** This domain occupies `0049a–0049z` (tables), `0150–0154` (business views) and its slices of `0140–0149` (functions/triggers). **Nothing may be written at `0200` or above.** See the binding block at the end of this document. | The goal is unchanged — zero file collision, zero object-name collision, forward-only numbering preserved — but `0200+` was carved out of a range `ARCHITECTURE.md` §18 never defined, and an unowned range is what produced two conventions. The grant now lives in `migrations.allocation.toml` and is enforced by `trappoint migrate lint`, not by a sentence |
| D10 | **No trigger in this domain depends on inter-trigger firing order.** Ordering is measured (`GT-A1`) and recorded, never relied on | CockroachDB does not document multi-trigger firing order for v26.2; PL-3 forbids a dated path on an unproven capability |
| D11 | **`identity_policy-v1.toml` (thresholds, bands, ε) is content-hashed onto every `identity_assignment` row** | Retro-tuning the matcher to make a drop look reasonable becomes visible the same way M3 makes τ-tuning visible |
| D12 | **The oracle (Path B) is built cassette-first**; the live Bedrock path exists but is off by default and is never exercised in CI | AWS credentials are not yet valid; PL-3. Cassettes are keyed `sha256(prompt‖model‖prompt_version)` and committed, matching the corpus discipline already chosen |
| D13 | **Two mutation catalogues, one harness: KILL (control mutations must be caught) and SURVIVE (reflow mutations must not change identity)** | The two failure directions are different products — one is a missed weakening, one is a manufactured false positive — and a single "accuracy" number hides both |

---

## 2. The named algorithms, their enforcement, and their honest prior-art position

Every entry ships a `novelty/<slug>.yaml` fragment (schema in §6) that CI validates. **Anything that is a re-parameterisation of known work is labelled as such in that file and in `MECHANISMS.md`.**

| Name | What it is | What the DB can now refuse | Prior-art position |
|---|---|---|---|
| **CANONHOLD** | versioned canonicaliser; numbering prefixes excised into their own field; OCR confusable repair only inside numeric token classes; FastCDC fallback segmentation | (feeds identity) | **Re-parameterisation.** NFKC + FastCDC + layout-first ingest are known. The only unclaimed part is `canon_version` being a *migration*, not a config flag |
| **ANCHORLOCK** | 7 model-free hard-anchor classes; anchors **veto** a semantic match; uncompensated anchor drop raises `weaken` on its own | `identity_residue.reason='anchor_drop'` → `identity_conserved_when_issued` (23514) | **Unclaimed coupling.** Gazetteer NER is old; using it as a *veto over cosine* and as an *independent weakening signal* is not something the surveyed document-control systems express |
| **DIRECTRIX** | `safe_direction(parameter)` registry self-hosted as clauses in the gated DAG with its own blame edges and a signed ratification commit | a `restate`/`strengthen` verdict citing an unratified parameter is refused (P0001) | **Novel as far as this survey found.** The recursion — the gate's parameter table is gated by the gate — is the claim, not the registry |
| **CATSEAL** | Control Assertion Tuple; length-prefixed typed preimage; `cat_key` as identity axis 2 | (feeds identity axis 2) | **Composition.** MeasEval-style quantity-and-context extraction + deontic taxonomy are published; hashing the tuple into a second identity axis that blame attaches to is unclaimed |
| **DELTALATTICE** | 9 deterministic rules over two CATs → `(delta, minimal witness set)` | D8: a witness-free lattice `weaken` cannot be inserted (P0001); a `weaken` over sev≥4 ancestry materialises the blocking check (23514 / MI30) | **Unclaimed.** Deontic downgrade detection exists in legal NLP; a *lattice with a minimal unsatisfiable witness whose absence is a write refusal* does not |
| **ABSTENTION RATCHET** | Path A ⊕ Path B resolution whose codomain is monotone-upward in force; abstention resolves to `weaken`; every `neutral` and every abstention writes its arithmetic | (guarantees the model can never *lower* a verdict — proven by test, not asserted) | **Re-parameterisation of selective prediction**, with teeth. Labelled as such. The teeth (a merge refusal) are the unclaimed part |
| **ORIGINDIFF** | delta computed against the **blame-origin version**, not the parent | twenty individually-neutral commits whose composition weakens are refused | **Novel in this application.** Falls out of diachronic gating; no synchronic system can express it |
| **COMMUTATION FOOTPRINT** | two clause edits commute iff their (anchor ∪ CAT-parameter) footprints are disjoint; non-commuting pairs are *derived* dependency edges (I06) | widens the antecedent set the weaken gate reads; the refusal itself remains the existing gate | **Transplant.** Darcs/Pijul patch commutation is published; applying it to safety-control footprints to derive blame antecedents is unclaimed. Labelled a transplant |
| **MARGIN ASSIGNMENT** | sparse LAP over cascade survivors; split/merge admitted under anchor containment; **degeneracy ⇒ residue, never a tie-break** | `identity_residue.reason='ambiguous'` → 23514 | **Unclaimed rule.** Assignment-based matching is standard; refusing to resolve a degenerate optimum, and treating that refusal as the product, is not |
| **CBM LEDGER** | the conservation identity `inherited = carried + split + merge + residue_open + residue_disposed` as a projected, trigger-derived `CHECK` | `cbm_balanced_when_issued` (23514) and a missing account refuses the merge (P0001) | **The flagship.** No prior art found for a conservation law over blame obligations enforced as a database constraint |
| **MUTATION RATCHET** | KILL/SURVIVE catalogues, Wilson-bounded kill rate per mutation class, published as a standing metric | (measures; never gates) | **Re-parameterisation** of software mutation testing onto safety controls. Labelled as such. The unclaimed part is publishing the residual-risk number instead of a launch claim |

---

## 3. Sequencing, and where the red tests go

**PL-2 binds every worker: the first artefact is the failing test its exit criterion asserts.** For this domain the deliverable is a refusal or a residue row, so a suite that has never been red asserts nothing.

```
 W1 canon-anchors ─┬─► W2 quantity-directrix ─┐
                   │                          ├─► W3 cat-seal ─► W4 delta-lattice ─┬─► W5 abstention-ratchet ─┐
                   │                          │                                    └─► W6 origin-diff         │
                   └─► W7 candidate-cascade ─► W8 margin-assignment ─► W9 cbm-enforcement                     │
                                                                                                              ▼
                                                                                        W10 mutation-ratchet ◄─┘
```

Proven-before order, and the exact first red test per worker:

| Order | Worker | First failing test (must be red before any implementation) |
|---|---|---|
| 1 | `canon-anchors` | a retypeset+renumber+OCR-noise triple of the same clause must produce **one** `canon_sha256`; and a paraphrase that changes `P-101A` → `P-101B` must produce an anchor-incompatible verdict |
| 2 | `quantity-directrix` | `Quantity(50, 'psig')` converted to `kPa` **raises**; and `safe_direction` lookup of an unratified parameter returns `ABSTAIN`, not a default |
| 3 | `cat-seal` | a committed golden vector's `cat_key` mismatches (empty implementation) — byte-exact preimage first |
| 4 | `delta-lattice` | `MUST → SHOULD` with everything else identical returns `weaken` with exactly one witness; and a `weaken` verdict with an empty witness set raises |
| 5 | `abstention-ratchet` | the resolution table must contain **no cell** where an oracle output lowers the Path-A force; a property test over the full product of inputs is red until the table exists |
| 6 | `origin-diff` | a 20-step chain of individually-`restate` edits whose composition is a deontic downgrade returns `weaken` at step 20 |
| 7 | `candidate-cascade` | a cosine-0.97 candidate with a conflicting equipment tag must be **rejected**, not accepted |
| 8 | `margin-assignment` | a constructed degenerate cost matrix (two equal optima) must emit `ambiguous` residue and **zero** assignment edges |
| 9 | `cbm-enforcement` | delete one `identity_residue` row that the account counted → `INSERT INTO cbm_account` returns `23514`; and a merge with no account returns `P0001` **naming the constraint** |
| 10 | `mutation-ratchet` | the harness must first report a **surviving** mutant (kill rate < 1.0) on a deliberately weakened lattice — a harness that has only ever reported 100 % is not a harness |

**K-milestone mapping.** W1–W4, W6–W9 are K3 (`G3` exit criteria 1, 2, 4, 5, 6). W5 is K3/K5 boundary. W7's semantic arm consumes fixtures at K3 and the live index at K4. W10 is K3-seeded, K8-standing.

---

## 4. Interfaces — frozen here so ten workers compose

`mainline_domain/contracts.py` is written **once, by W1**, and imported by everyone. No other worker may add to it; if a worker needs a new shared type, it defines it in its own subpackage. Frozen dataclasses, `slots=True`, no defaults on identity-bearing fields.

```python
ControlDelta = Enum("introduce","strengthen","restate","weaken","remove")   # mirrors mainline.control_delta
def force(d: ControlDelta) -> int: ...   # introduce/restate/strengthen = 0, weaken = 2, remove = 3

CanonResult(canon_text, canon_sha256, canon_version, numbering_prefix, printed_label,
            furniture_spans, ocr_repairs, segments)
AnchorClass = Enum("equipment_tag","setpoint","regulatory_citation","cas","named_role",
                   "instrument_loop","isolation_point_id")
Anchor(cls, raw, norm, span)                    # norm is the identity form; identity classes exclude 'setpoint'
AnchorSet(items: frozenset[Anchor])             # .by_class(), .identity_norms(), .compatible_with(other) -> bool
Quantity(value: Decimal, unit: str, dimension: str,
         reference: Literal["absolute","gauge","delta","none"])
CAT(actor, deontic, action, object_class, hazard_energy, parameter, comparator,
    value: Quantity|None, conditions: tuple[str,...], exceptions: tuple[str,...],
    verification: tuple[str,...], frequency: Quantity|None, coverage_quantifier)
CATResult(cat: CAT|None, confidence: Literal["ok","low","opaque"], evidence_spans, extractor_version)
DeltaWitness(rule_id, field, from_repr, to_repr, note)     # rule_id ∈ R1_DEONTIC … R9_COVERAGE
DeltaVerdict(delta, basis: Literal["lattice","lattice+model","abstain_to_weaken","human"],
             witnesses: tuple[DeltaWitness,...], minimal: bool)
OracleVerdict(label, confidence: float, rationale, cited_spans, model_id, prompt_version, abstained: bool)
Candidate(ancestor_clause_uuid, ancestor_commit, stage, score, features: Mapping[str,float])
AssignmentEdge(ancestor_clause_uuid, descendant_clause_uuid|None,
               relation: Literal["matched","split","merge","absent"], stage, score, margin)
ResidueRow(ancestor_clause_uuid, reason, match_score, features)   # reason ∈ the five values in the DDL CHECK
CBMAccount(site_id, commit_id, inherited, carried, split_carried, merge_carried,
           residue_open, residue_disposed)
class DeltaOracle(Protocol):  def classify(self, req: OracleRequest) -> OracleVerdict: ...
class PrefixArmRunner(Protocol): def ann(self, site_id, activity_root, q, k) -> Sequence[Candidate]: ...
```

**Boundary note.** `ResidueRow.reason` must be one of the five values already in the `identity_residue` `CHECK` (`unmatched`, `ambiguous`, `anchor_drop`, `opaque_control`, `citation_unresolved`). No worker may propose a sixth; `cat_confidence='opaque'` maps to `opaque_control`.

**`max_ancestral_severity` is a projection, not an input.** The DDL in §5.3 annotates it `PROJECTED from clause_blame_closure (P2)` but §5.11 lists no trigger that projects it — only `fn_residue_counter`, which counts. **This is a P2 hole and this domain closes it** (`fn_residue_project`, W9; ~~migration 0204~~ → an unwritten file in `0140–0144`, per the binding block at the end of this document): the trigger re-derives severity from `clause_blame_current` for the ancestor's version in the first-parent commit and `RAISE`s when no closure row exists.

---

## 5. Turning CBM from a narrative into a `CHECK`

The architecture already gives residue a refusal (`identity_conserved_when_issued`). What it does not give is a guarantee that **residue emission was complete** — a projector that under-emits residue produces a clean gate. That is the one place where the flagship claim is currently only as strong as the code that wrote the rows.

The fix is the kernel idiom applied to the accounting itself:

- **PROJECT** — `fn_cbm_account_guard` (BEFORE INSERT on `mainline.cbm_account`) **recomputes** `inherited`, `carried`, `split_carried`, `merge_carried`, `residue_open`, `residue_disposed` from `clause_blame_current`, `identity_assignment` and `identity_residue`, overwrites whatever the inserter supplied, and `RAISE`s if the authoritative sources are missing. Never trusts the projector process.
- **REFUSE (structural)** — `mainline.cbm_account` carries `balanced BOOL AS (inherited = carried + split_carried + merge_carried + residue_open + residue_disposed) STORED` and `CONSTRAINT cbm_balances CHECK (balanced)`. Under-emitting residue is `23514` at the moment of accounting, not at merge.
- **REFUSE (gate)** — `permit.unbalanced_cbm_count` / `change_request.unbalanced_cbm_count` (new column, new constraint name; ~~added in band 0203~~ → `permit` and `change_request` are RENDERED substrate, so this is a template edit agreed with `kernel/subject-and-pin` and re-rendered into both bindings, per the binding block at the end of this document) projected by `fn_cbm_project`, with `CONSTRAINT cbm_balanced_when_issued CHECK (state <> 'merged' OR unbalanced_cbm_count = 0)`; plus trigger `z_cbm_gate` raising `P0001` when a subject's cited commits have **no** account at all. Refusal depth 2, order-independent (D10).

Consequence, stated the way it will be said under oath: *"the merge was refused by `cbm_balanced_when_issued`, because the commit's blame accounting did not balance — five obligations went in and four came out."*

---

## 6. `novelty/*.yaml` — the fragment the build consumes

One file per algorithm, per worker, so ten workers never touch one manifest. Validated by `tests/unit/domain/novelty/test_novelty_manifest.py` (W10) and consumed by `MECHANISMS.md` generation.

```yaml
slug: cbm-ledger
name: CONSERVATION OF BLAME MASS LEDGER
mechanism: M1
claim: "the blame conservation identity is enforced as a database CHECK, so under-emitting residue is 23514"
enforcement:
  refuses: ["cbm_balances (23514)", "cbm_balanced_when_issued (23514)", "z_cbm_gate (P0001)"]
  refusal_depth: 2
position: unclaimed          # one of: unclaimed | composition | transplant | re-parameterisation
prior_art:
  - url: "..."
    what_it_covers: "..."
    what_it_does_not: "..."
implemented_by: ["verticals/mainline/db/migrations/0201_cbm_account.sql", "..."]
tests: ["tests/integration/algorithms/cbm/test_balance_refusal.py::test_underemitted_residue_23514"]
unverified: []               # anything not yet proven goes HERE, never in the claim field
```

---

## 7. Worker roster

| ID | Worker | One-line purpose |
|---|---|---|
| W1 | `canon-anchors` | the model-free floor: versioned canonicalisation + the seven hard-anchor classes + the shared `contracts.py` |
| W2 | `quantity-directrix` | SI/gauge-safe quantity algebra and the `safe_direction` registry self-hosted in the gated DAG |
| W3 | `cat-seal` | the Control Assertion Tuple: deterministic extraction, byte-exact preimage, `cat_key`, opacity policy |
| W4 | `delta-lattice` | the nine-rule deterministic `control_delta` lattice with a minimal witness set, and the witness-or-refuse trigger |
| W5 | `abstention-ratchet` | the independent LLM path in its own package + the monotone-upward, fail-closed resolution that the model can never lower |
| W6 | `origin-diff` | blame-origin resolution, ancestral CAT diff (salami defence), and commutation-footprint derived dependency |
| W7 | `candidate-cascade` | cascade stages S1–S4: exact, anchor, MinHash/LSH banding, anchor-gated ANN over `clause_embedding` |
| W8 | `margin-assignment` | sparse LAP with split/merge under anchor containment, degeneracy-as-residue, the cascade orchestrator, residue emission |
| W9 | `cbm-enforcement` | the conservation identity as SQL: account table, projecting guard, subject counters, `fn_residue_project`, audit view |
| W10 | `mutation-ratchet` | KILL/SURVIVE mutation catalogues, Wilson-bounded standing metric, nightly workflow, novelty-manifest validator |

---

## 8. Risks accepted

| # | Risk | Position |
|---|---|---|
| R-A1 | **Delta false negatives** — a real weakening classified `restate` by both paths. Irreducible | Not argued away; **measured** by the mutation ratchet and published per mutation class with Wilson bounds. It is the residual risk and it is named in the honesty card |
| R-A2 | **False merge** — blame jumps to the *wrong* clause. CBM does not protect against this (`BUILD_PLAN` K3 "fails how") | Pre-committed escalation ladder: raise the auto-accept band → disable the semantic stage → run on hash + anchors only. The gate gets louder and dumber and stays honest. `identity_policy` version is on every row so the ladder is auditable |
| R-A3 | **Representation FN** — controls in tables, P&IDs, cross-references the extractor cannot parse | `cat_confidence='opaque'`; any edit to an opaque clause with sev≥4 ancestry defaults to `weaken`. Deliberate over-blocking, stated as a product characteristic |
| R-A4 | **DIRECTRIX coverage** — a few hundred parameters per site is hard engineering, not research, but it is still work | D6 makes under-coverage fail *closed*, so the cost is nuisance blocks, not silent passes. Adoption ratchet: ratify to un-block |
| R-A5 | **Trigger firing order undocumented on v26.2** | D10: nothing depends on it. `GT-A1` measures and records it; if the observed order is unfavourable the demo narration changes, not the design |
| R-A6 | **`levenshtein()` bounds and trigram gaps in CockroachDB** (`<->` family unsupported; `word_similarity` unsupported) | Edit distance is computed in the application (`rapidfuzz` 3.14.x); SQL uses `%` to filter and `similarity()` to score only. No query in this domain orders by trigram distance |
| R-A7 | **Adjudication load** — CBM deliberately converts recall failure into blocking rows | Bounded by the permit slice (§5.5) and by the nuisance ceiling in §6.7. If the ceiling breaks, the rule is **rejected, not tuned** |
| R-A8 | **The honest limit** — none of this distinguishes a considered disposition from a rubber stamp | Stated in `novelty/*.yaml` `unverified` fields and in the README. The identity machinery must never be sold as retiring that risk |

---

## 9. Migration band reservation — ⚠ REVOKED 2026-08-08

> **THIS SECTION IS REVOKED IN WHOLE AND GRANTS NOTHING.** It is retained as the record of what
> was planned. **REVOKED: this domain does not write `0200–0219`.** **REVOKED and refused by lint:
> no file may be written at `0200` or above**, in either authoring mode. The replacement grants — `0049a–0049z`, `0150–0154`, and slices of `0140–0149` — are in
> `verticals/mainline/db/migrations.allocation.toml`, which is the authority, and they are
> restated in the binding block at the end of this document. **Read that block before allocating
> a single number.** The three files this section already produced have moved:
> `0205 → 0049a`, `0207 → 0150`, `0211 → 0140 + 0145`.

The original reservation, struck:

```
~0200~ identity_assignment                              W8    → unnumbered; take a number from 0049a-0049z
~0201~ cbm_account (+ balanced STORED + cbm_balances)   W9    → unnumbered; take a number from 0049a-0049z
~0202~ fn_cbm_account_guard + trigger                   W9    → unnumbered; 0140-0144 fn, 0145-0149 trg
~0203~ ALTER permit / change_request                    W9    → NOT a vertical migration: permit and
                                                                change_request are RENDERED substrate.
                                                                This is a template edit agreed with
                                                                kernel/subject-and-pin, re-rendered into
                                                                BOTH bindings.
~0204~ fn_cbm_project + fn_residue_project + triggers   W9    → unnumbered; 0140-0144 fn, 0145-0149 trg
~0205~ delta_witness                                    W4    → 0049a_delta_witness.sql
~0206~ commutation_edge                                 W6    → unnumbered; take a number from 0049a-0049z
~0207~ v_safe_direction_current                         W2    → 0150_v_safe_direction_current.sql
~0209~ mainline_meas.mutation_run / mutation_result     W10   → unnumbered; take a number from 0049a-0049z
~0210~ mainline_audit.v_cbm_ledger                      W9    → unnumbered; 0150-0154
~0211~ fn_delta_witness_guard + trigger                 W4    → 0140_fn_delta_witness_guard.sql
                                                              + 0145_trg_delta_witness_guard.sql
~0212~ v_blame_origin                                   W6    → unnumbered; 0150-0154
```

The two properties this section was reaching for are unchanged and are now enforced rather than
asserted: one statement per file, each citing at least one invariant ID in a header comment, each
owned by exactly one worker; and nothing in this domain's bands alters an existing column or
constraint — with the one exception now made explicit above, `permit`/`change_request`, which are
substrate and are therefore reached through a template, never through an `ALTER` typed into the
vertical.

---

# ⚠ PLATFORM GROUND TRUTH — MANDATORY, SUPERSEDES ANY CONFLICTING ASSUMPTION ABOVE

**Measured against the live cluster on 2026-08-07. See `docs/adr/0002-g1-platform-ground-truth.md`.
These are MEASUREMENTS, not documentation. Where your brief or this plan assumed otherwise, THESE WIN.**

**Cluster:** CockroachDB CCL **v26.2.5**, cluster version 26.2, **Basic tier**, `aws-ap-southeast-1` (**Singapore**).
**Bedrock:** `ap-southeast-2` (Sydney), 8 `au.*` Claude profiles ACTIVE (incl. `au.anthropic.claude-sonnet-5`, `au.anthropic.claude-opus-5`).

## F1 — Vector index WORKS on Basic, but the optimizer will not choose it

`feature.vector_index.enabled` is **`true` by default**. `VECTOR(n)` columns and prefix-column vector indexes **create and populate successfully on the free Basic tier**. The largest platform risk is retired.

**BUT:** at 5,200 rows an unhinted prefix-constrained ANN query does **NOT** use the index — the plan is `top-k → render → filter → scan`. The index is traversed **only** when named explicitly:

```sql
SELECT id FROM tbl@tbl_prefix_emb_idx
WHERE tenant = $1 AND state = $2          -- every prefix column = a single value
ORDER BY emb <=> $3 LIMIT $4
```

**RULING:** every ANN arm **pins the index explicitly**. Any CI assertion of the form "EXPLAIN proves the ANN uses the index" must assert traversal of the **named, hinted** index — an unhinted assertion fails at demo corpus scale. This is also the more deterministic engineering: a plan that flips on table statistics must not sit beneath a safety gate.

The `IN (...)` trap is UNCHANGED: every prefix column must still be constrained to a single value, so an ancestor walk is one hinted ANN query per ancestor, `UNION ALL`-ed and re-ranked.

Tunable session vars confirmed present: `vector_search_beam_size = 32`, `vector_search_rerank_multiplier = 50`.

## F2 — The time-travel window is 75 minutes, not 4 hours

`gc.ttlseconds = **4500**` on this cluster (the architecture assumed 14400). **`AS OF SYSTEM TIME` cannot reach beyond ~1 hour.** All long-horizon versioning is the application-level commit DAG. No demo beat, claim, exhibit or test may depend on time-travel reaching further. Verified live: a query past the window is **refused**, not silently wrong — keep that as a conformance case.

## F3 — Confirmed available (build against these freely)

| Capability | Status |
|---|---|
| PL/pgSQL triggers with `RAISE EXCEPTION` | ✅ PASS |
| **CTE inside a UDF** | ✅ PASS — the "no CTE in UDFs" claim was stale (removed v25.1) |
| `ALTER TABLE … ENABLE ROW LEVEL SECURITY` | ✅ PASS |
| `STORED` computed column with `digest()` | ✅ PASS — the `dedupe_key` fix (finding S5) is implementable |
| Partial `UNIQUE` index | ✅ PASS — the one-custodian invariant is implementable |
| `kv.rangefeed.enabled` | ✅ `true` — changefeeds available |
| `amazon.titan-embed-text-v2:0` in ap-southeast-2 | ✅ PRESENT (closes a previously-flagged unverified item) |
| `cohere.embed-v4:0` in ap-southeast-2 | ✅ PRESENT — not in the original design; a benchmark candidate, not a default |
| Bedrock Rerank in ap-southeast-2 | ❌ ABSENT, as assumed. Take no dependency |

## F4 — `CREATE SEQUENCE` succeeds on this cluster

The CI lint banning `CREATE SEQUENCE` / `nextval(` / `SERIAL` / `unique_rowid()` is therefore **load-bearing, not decorative**. Gap-free-by-CAS is only meaningful while that lint holds.

## F5 — Residency: inference in Australia, database in Singapore

Sydney (`ap-southeast-2`) is **Advanced-tier only** — absent from the Basic and Standard region lists. **Any claim of end-to-end Australian data residency is FALSE for this deployment** and must not appear in the README, submission, video, console, or any comment. State the split precisely wherever residency is mentioned.

---

# MIGRATION RECONCILIATION RULING — 2026-08-08, BINDING, SUPERSEDES THE BANDING SECTION ABOVE

<!-- ────────────────────────────────────────────────────────────────────────────────────
     THIS BLOCK IS REPRODUCED WORD FOR WORD IN FIVE LEAD PLANS:
       docs/leads/kernel.md · datamodel.md · algorithms.md · recall.md · custody.md
     Everything down to "END OF THE COMMON BLOCK" is byte-identical in all five by
     construction. If you are holding a copy that differs from another copy, the
     difference IS the error — go to the source, not to the copy.

     Source of truth for this ruling : docs/leads/migration-reconciliation.md
     Machine-readable authority      : verticals/mainline/db/migrations.allocation.toml
     Generated manifest of the tree  : verticals/mainline/db/migrations.lock.json
     ──────────────────────────────────────────────────────────────────────────────────── -->

**Why this block exists, in one paragraph.** Two domains independently implemented the same
section of the migration order, under two conventions and at two granularities, because two lead
briefs were given overlapping ownership of the migration number space. One side declared ownership
as numeric *bands* (`0050–0065`), the other as literal *file paths* (`0006a_role_migrator.sql`).
The pre-dispatch collision check compared those two declarations as strings, found nothing in
common, and reported **zero collisions**. It was wrong by twenty numbers, and the tree it produced
would not `discover()` at all. Nothing below is a style preference. Each ruling is the mechanical
form of a failure that has already happened once, and each is enforced by a command rather than by
a reader's memory.

**This block does not touch the PLATFORM GROUND TRUTH findings (F1–F6) at the end of this
document. Those are measurements against v26.2.5 and they still win over everything, including
this.**

## MR-1 — the seam: RENDERED or AUTHORED, decided by OBJECT

> **`verticals/mainline/db/migrations/` has exactly two kinds of file, and every number in the
> sequence belongs to exactly one of them: RENDERED (emitted by a template in
> `packages/trappoint-sql/templates/`, never hand-edited) or AUTHORED (written directly in the
> vertical, never emitted). The seam is drawn by OBJECT, not by worker and not by band, and the
> object test is: _would a second TRAPPOINT vertical need this object to pass `trappoint-conform`?_
> If yes it is SUBSTRATE and it is a template. If no it is VERTICAL and it is authored.**

Apply the test to the object, not to yourself. "I am a kernel worker" and "I am a datamodel
worker" are not inputs to it; `permit` is substrate whoever types it, and `site` is vertical
whoever types it. MR-2 fixes the substrate list — the five schemas; the nine roles and the
privilege floor; the seven enum types; `subject_transition` (+seed); `clearance_legal` (+seed);
`person`; `signing_credential`; `permit`; `change_request`; `permit_clause`; `cr_clause`;
`permit_event`; `cr_event`; `blocking_check`; `exposure_receipt`; `exposure_line`;
`receipt_expiry`; `defeater_option`; `disposition`; `disposition_citation`; `override_ledger`;
`merge_record` + its two epoch-pin FKs; `refusal_ledger`; the projection function/trigger family;
the merge procedures and merge-gate triggers; the gap-free CAS append function — and **everything
else in MAINLINE is VERTICAL.**

Three consequences that are not negotiable:

1. **A rendered file is never deleted to resolve a collision — the next `trappoint render`
   recreates it.** The kernel side of every collision in this incident was rendered output; it was
   never hand-written into the migrations directory. A plan that says "delete the kernel's
   `0006a…0006i`" is a plan that fails on the next render.
2. **A hand-authored twin of a rendered file is permanently red, and red in the worst way.**
   `trappoint render --check` is a zero-diff assertion; a twin under a different suffix is not a
   diff, so `--check` stays green while the *runner* refuses the tree. CI green, deploy dead.
3. **A change to a rendered file is a change to its template, followed by a re-render of BOTH
   bindings** (`verticals/mainline/vertical.toml` and
   `packages/trappoint-sql/refvertical/vertical.toml`). Two bindings that both render is the entire
   substrate claim; one binding is a template engine with an audience of one.

## MR-5 — THE ONE FILENAME CONVENTION

```
NNNN[a-z]_lower_snake_slug.sql
```

Stated exactly:

* **`NNNN`** — exactly four decimal digits, zero-padded, allocated by the table in §3/§4 of
  `docs/leads/migration-reconciliation.md` and by its machine-readable form
  `verticals/mainline/db/migrations.allocation.toml`.
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
  `.v2.sql` fail `_VERSION_RE` and make the entire directory undiscoverable (measured: one such
  filename made `trappoint migrate` refuse all 121 files beside it). Capability variants live in
  `verticals/mainline/db/ext/<topic>/` and are selected by a render-time switch (kernel D5), never
  by a file in the apply path.
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

`.up.sql` is a `trappoint migrate lint` **failure** today (rule C, `up-sql-suffix`). That rule was
deliberately red on this tree until the renames landed: a guard that was *observed* red is a guard
that asserts something, and there is no exemption list, no warning level and no environment
variable that downgrades it.

## MR-6 lock 1 — `migrations.allocation.toml` is the authority for numbers

**`verticals/mainline/db/migrations.allocation.toml` is the authority for migration numbers, and
it is enforced by `trappoint migrate lint`.** The band tables in the prose — in the reconciliation
ruling, in this plan, in any plan — are its *rendering*. Where prose and that file disagree, the
file is what lint enforces and the file is therefore what is true.

Lint resolves every discovered file against it and refuses three things:

* **Rule A · `filename-convention`** — the filename must match `^\d{4}[a-z]?_[a-z0-9_]+\.sql$`.
* **Rule B · `allocation-mode` / `allocation-unallocated`** — the file's `(NNNN, letter)` key must
  fall in a band, and the band's `mode` must agree with the file: a file carrying
  `-- @rendered-by  trappoint render` in an `authored` band is a refusal, and so is a file without
  that banner in a `rendered` band. **This is the rule that compares a file against a declaration
  rather than comparing two declarations with each other, which is the thing the collision check
  could not do.**
* **Rule C · `up-sql-suffix`** — `.up.sql` is a failure.

Two further consequences of the authority sitting in one file:

* **`0200` and above is UNALLOCATED and no file may use it, in either mode.** A number space with
  no owner is exactly what produced two conventions; a range that lint refuses is safer than a
  range someone can assume into.
* **Adding or moving a band is not an edit to that file alone.** A new band is carved out of an
  existing one, both sides are restated, and the result must remain exhaustive and disjoint over
  the whole key space — `packages/trappoint-migrate/tests/test_allocation.py` refuses an overlap
  and refuses a gap. A worker who needs a number that is not theirs asks the band's owner; a worker
  who has run out of numbers suffixes their own last number (MR-5's band overflow).

`verticals/mainline/db/migrations.lock.json` is **generated** by walking
`trappoint_migrate.discovery.discover()` over the tree and resolving each file against the
allocation. It is a manifest, not a declaration: a lock file that is hand-written is a second
source of truth, which is the class of failure this ruling exists to end.

<!-- ──────────────────────────── END OF THE COMMON BLOCK ──────────────────────────── -->

## What this changes in THIS plan — algorithms

**D9 and §9 are revoked. The `0200–0219` annexe does not exist.** REVOKED because
`ARCHITECTURE.md` §18 never defined a `0200+` space — the annexe was carved out of an unowned
range, which is precisely the condition that produced two conventions in the first place. REVOKED
and refused: `0200`+ is now `UNALLOCATED` in `migrations.allocation.toml`, and lint refuses any
file that claims it, in either authoring mode. D9's stated goal — "zero
file collision, zero object-name collision, forward-only numbering preserved" — is unchanged and
is now enforced by rule B instead of by a sentence.

**This domain's replacement grants, explicit and exclusive:**

| Band | Contents |
|---|---|
| `0049a`–`0049z` | **the algorithms table annexe.** `delta_witness` = `0049a`. Granted to this domain alone; `0047`–`0049` (bare) is `dm-spine`'s and its `last` endpoint is a bare number precisely so that this letter space is unambiguously yours. |
| `0150`–`0154` | **`mainline.*` business views.** `v_safe_direction_current` = `0150`. |
| slices of `0140`–`0149` | **vertical functions (`0140`–`0144`) and vertical triggers (`0145`–`0149`)**, shared with `datamodel/dm-functions-triggers`. `fn_delta_witness_guard` = `0140`; `trg_delta_witness_guard` = `0145`. |

**The three files already on disk move, and one of them splits:**

* `0205_delta_witness.sql` → **`0049a_delta_witness.sql`**. A `CREATE TABLE` must live in the table
  space — after `0029 clause_version`, which it references, and before the gate.
* `0207_v_safe_direction_current.sql` → **`0150_v_safe_direction_current.sql`**.
* `0211_fn_delta_witness_guard.sql` → **`0140_fn_delta_witness_guard.sql`** +
  **`0145_trg_delta_witness_guard.sql`**. It carried two top-level statements, which breaks the
  one-statement rule, and it carried a `CREATE FUNCTION` inside a file numbered in a trigger band,
  which inverts §18's stratification. The split fixes both at once.

The remaining §9 rows are **unwritten and unnumbered**, and they are named here by object rather
than by their struck numbers so that no reader can lift a number out of this paragraph:
`identity_assignment`, the CBM family (`cbm_account`, `fn_cbm_account_guard`, `fn_cbm_project`,
`fn_residue_project` and their triggers), `commutation_edge`, `mainline_meas.mutation_run` /
`mutation_result`, `mainline_audit.v_cbm_ledger`, `v_blame_origin`. They are not cancelled — the
objects are still this domain's to build — but they take their numbers from the three bands above
when they are written. One of them changes shape rather than number: the
`ALTER permit / change_request` that adds `unbalanced_cbm_count` and `cbm_balanced_when_issued` is
now an edit to a **rendered substrate table**, and therefore an edit to
`packages/trappoint-sql/templates/`, agreed with `kernel/subject-and-pin` and re-rendered into both
bindings. It is not an `ALTER` typed into the vertical.

**This is not the band-borrowing that caused the incident, and the difference is worth stating.**
`0049a` sits inside what a reader of the old §3 table would call `dm-spine`'s range, and `0150`
sits inside what a reader would call the function/trigger tail. Both are granted to this domain
**explicitly and exclusively** by `migrations.allocation.toml`, and lint rule B enforces the grant
against every file on disk. Band borrowing failed because it was undeclared, not because it
happened.

D10 is unaffected: no trigger in this domain depends on inter-trigger firing order, and
`trg_delta_witness_guard` at `0145` still asserts nothing about what fires around it.

---

*Migration reconciliation, 2026-08-08. One convention, one authoring mode per number, one owner per band, and a lint that fails before a human has to notice. The collision check reported zero because it compared strings; the replacement compares a file against a declaration.*
