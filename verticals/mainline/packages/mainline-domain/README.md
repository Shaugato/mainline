<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-domain` — the deterministic, model-free floor

This distribution holds **the arithmetic that decides whether an edit to a safety control is a
weakening, and whether a blood-written obligation survived that edit at all**. Worker W1
(`canon-anchors`) ships the floor every other worker in the algorithms domain stands on:

| Module | Algorithm | What it produces |
|---|---|---|
| `mainline_domain.contracts` | — | the frozen shared vocabulary, transcribed from `docs/leads/algorithms.md` §4 |
| `mainline_domain.canon` | **CANONHOLD** | `canon_text`, `canon_sha256`, `canon_version`, `printed_label`, segments |
| `mainline_domain.anchors` | **ANCHORLOCK** | the seven hard-anchor classes, the compatibility veto, uncompensated-drop detection |

Authority: `ARCHITECTURE.md` §5.3 (the `clause_version` columns this package fills:
`canon_text` / `canon_version` / `canon_sha256` / `anchor_set` / `printed_label`), §3 (the
mechanism set), §16 (invariants); `docs/leads/algorithms.md` §2 (the CANONHOLD / ANCHORLOCK
rows and their honest prior-art position), §4 (the interfaces, frozen), §7 (the roster);
`research/05-architecture/clause-identity.md` §3, §5.

---

## Three rules that are not negotiable in this package

1. **No model SDK, ever.** Not `boto3`, not `anthropic`, not `strands`, not transitively.
   The lattice in this distribution decides a state transition, and P7 forbids any component
   that decides a state transition from reaching a model. Path B lives in the physically
   separate distribution `mainline-delta-oracle` and enters only through the
   `contracts.DeltaOracle` `Protocol`. Enforced by
   `tests/unit/domain/anchors/test_contracts.py::test_no_model_sdk_reachable_from_contracts`.
2. **No builtin `hash()`.** It is salted per process; every digest here is `hashlib`
   (`sha256` for identity, `blake2b` for the gear table and token bucketing) because the
   outputs are evidence an opposing expert has to be able to recompute. Enforced by
   `tests/unit/domain/canon/test_canon_version.py::test_no_builtin_hash_anywhere_in_the_package`.
3. **`contracts.py` is written once and never extended.** Ten workers ship into this
   distribution; a shared type added ad hoc is a shared type nobody reviewed. A worker who
   needs a new type defines it in their own subpackage.

---

## CANONHOLD — `mainline_domain.canon`

```python
from mainline_domain.canon import canonicalise

result = canonicalise(raw_clause_text)
result.canon_text      # every offset in the system is an offset into this
result.canon_sha256    # clause_version.canon_sha256 (32 bytes)
result.printed_label   # '7.3.2(b)' — stored as presentation, never as identity
```

The pipeline runs in one fixed order, and each step is at its position because the next one
depends on it:

| # | Step | Module | Why here |
|---|---|---|---|
| 1 | strip page furniture | `furniture.py` | line-based, so it must run while lines still exist, and on raw text so its spans are real offsets |
| 2 | fold | `fold.py` | NFKC, smart quotes/dashes, ligatures, soft hyphen and the discretionary-break family |
| 3 | de-hyphenate across wraps | `dehyphen.py` | needs the line breaks step 2 deliberately left intact; join-or-keep is resolved against a committed domain lexicon |
| 4 | collapse whitespace | `pipeline.py` | after de-hyphenation — this is where reflow dies |
| 5 | repair OCR confusables | `ocr.py` | **before** numbering, so `1O.` becomes `10.` and is then seen as a label |
| 6 | excise the numbering prefix | `numbering.py` | to a fixpoint — this is what makes renumbering a non-event |
| 7 | digest | `digest.py` | domain-separated and version-bound |
| 8 | segment | `segment.py` | content-defined (FastCDC), and only when layout gave no boundary |

**Step 5 before step 6 is the subtle one, and it is what makes the canonicaliser idempotent.**
In the other order, `1O. Before ...` canonicalises to `10. Before ...` — text a *second* pass
would strip a label from. A canonicaliser whose second application disagrees with its first
produces digests that cannot be reproduced by an opposing expert, cannot be re-derived during a
re-normalisation migration, and cannot be checked by a verifier against a stored `canon_text`.

### `canon_version` is a migration, not a config flag

`CANON_VERSION` is an `int` constant in `canon/version.py`. It is never read from
`os.environ`, a TOML file, a CLI flag or a database row, and `canonicalise()` takes no version
parameter — one process, one canon version, decided at build time. The version is bound into
the digest preimage:

```
sha256( b"mainline/canon/v" || ascii(CANON_VERSION) || 0x1F || utf8(canon_text) )
```

so a bump moves every digest. That is the intended cost. Bumping it requires a migration that
re-canonicalises the affected `clause_version` rows, a re-run of the identity cascade over the
touched commits, and CBM accounts that still balance afterwards — because a silent bump would
make the S1 exact stage quietly stop matching, and a silent stop is the exact failure mode this
product exists to refuse. (`ARCHITECTURE.md` §18 folds `canon_version` into `parser_id` for the
same reason.) Enforced by `tests/unit/domain/canon/test_canon_version.py`.

### OCR repair never touches free prose

Confusable repair (`l`/`1`/`I`, `0`/`O`, `S`/`5`) fires only on a token whose core begins with a
digit, contains only digits/confusables/numeric separators, already holds at least one real
digit, and holds at least one confusable. `SO2`, `IS0`, `Oil`, `loss` and `SOLE` all begin with a
letter and are therefore unreachable. The cost is stated openly rather than hidden: damage to
the *leading* character of a number (`lO` for `10`) is **not** repaired, and a number glued to
its unit (`1O0kPa`) is not repaired. A missed repair costs a match and produces an adjudicable
residue row; a wrong repair silently rewrites a setpoint.

Repair is a 1:1 substitution, so it is length-preserving and never invalidates an offset.

---

## ANCHORLOCK — `mainline_domain.anchors`

```python
from mainline_domain.anchors import extract_anchors, uncompensated_drops

reference  = extract_anchors(origin_canon_text)     # blame-origin, not parent (W6)
descendant = extract_anchors(new_canon_text)

reference.compatible_with(descendant)        # False VETOES a semantic match
uncompensated_drops(reference, descendant)   # each one is a weaken candidate on its own
```

Seven classes, by regex plus committed TOML gazetteers under
`src/mainline_domain/data/gazetteer/`. Extraction runs most-constrained-first and a match
overlapping an already-claimed span is discarded:

```
cas > regulatory_citation > isolation_point_id > instrument_loop > equipment_tag > setpoint > named_role
```

**Five of the seven are identity classes** (`equipment_tag`, `isolation_point_id`, `cas`,
`regulatory_citation`, `instrument_loop`). Two are not:

- **`setpoint` is deliberately not an identity class.** A moved setpoint is the lattice's job
  (rule `R2_SETPOINT`), not the matcher's. Were it an identity class, every legitimate setpoint
  change would present as a non-match, and the weakening it represents would hide behind an
  `unmatched` residue row instead of being adjudicated as the weakening it is.
- **`named_role` is not either**, for the same reason against rule `R1_DEONTIC`.

**Conflict, not inequality.** Two sets conflict in a class when both carry an anchor of that
class and share none. So `P-101A → P-101B` is a conflict (a swap), while
`P-101A → P-101A, P-101B` is an extension and stays compatible. `compatible_with` is symmetric
and reflexive; it is **not** transitive, and nothing in the cascade may assume that it is.

**Unknown prefixes fail closed.** A hyphenated `LETTERS-DIGITS` token whose code appears in no
gazetteer is still extracted, as an `equipment_tag`. More anchors means more identity
constraints means more blocking — never less. The cost of that choice is nuisance adjudication;
the cost of the other choice is a tag that can be swapped without anyone noticing.

**CAS numbers are checksum-validated** against the published check-digit rule, because a false
CAS anchor is an identity-class anchor and identity-class anchors veto matches — a false one
manufactures residue for a clause nobody touched.

### Uncompensated drop

An identity anchor in the reference and absent from the descendant, with **nothing of its class
added in its place**, is an *uncompensated drop*: a `control_delta='weaken'` candidate with no
embedding, no lattice rule and no oracle involved. It writes
`identity_residue.reason='anchor_drop'`, which is what the merge gate refuses on.

"Compensated" means *an anchor of the same class was added* — not "an equivalent anchor was
added". This module does not attempt to decide equivalence, because deciding it wrongly is how
a swap gets waved through. A compensated drop is handed to `compatible_with`, which already
refuses to call a swap the same clause; that is the louder outcome.

---

## What this package does **not** do

Stated here because the claim would otherwise be read as larger than it is:

- **It writes no SQL and enforces no constraint.** Every refusal named in `novelty/*.yaml`
  is enforced by DDL owned by the kernel lead and by W9 (`cbm-enforcement`). This package
  produces the values those constraints read. Until those migrations land, the enforcement
  claims are listed under `unverified:` in the manifests and nowhere else.
- **It does not decide equivalence between two different anchors.** See above.
- **It does not treat `w14:paraId` — or any other word-processor-assigned paragraph id — as
  authority.** Those identifiers are assigned by an editor, survive a copy-paste, and are
  exactly the kind of thing an author can rewrite; identity here is derived from content, and
  from content only.
- **It does not repair damage inside an equipment tag.** `TK-2O4` stays as written. Tags are
  anchors, and a damaged anchor is better reported as an anchor drop than silently
  reconstructed into a *different* tag.

---

## Run it

```bash
uv run pytest tests/unit/domain -q            # 193 tests, no network, no cluster, no credentials
uv run mypy --strict src/mainline_domain      # from this directory
```

The exit criteria for this worker, and the tests that hold them:

| Criterion | Test |
|---|---|
| retypeset + renumbered + OCR-noised ⇒ **one** `canon_sha256` | `tests/unit/domain/canon/test_reflow_triple.py::test_three_forms_yield_one_canon_sha256` |
| `P-101A → P-101B` paraphrase is anchor-**incompatible** | `tests/unit/domain/anchors/test_anchor_incompatible.py::test_p101a_to_p101b_paraphrase_is_anchor_incompatible` |
| `canon(canon(x)) == canon(x)` over ≥1000 generated inputs | `tests/unit/domain/canon/test_idempotence.py::test_canon_is_idempotent` (1200 examples) |
| `mypy --strict` clean on `.canon`, `.anchors`, `.contracts` | CI |

Both exit-criterion tests were committed and run **before** the implementation existed
(PL-2 red-before-green); each records its red run in its module docstring. For a product whose
deliverable is a refusal, a suite that has never been red asserts nothing.

## Dependencies

`pyproject.toml` declares the **whole** domain dependency set — `pint`, `scipy`, `numpy`,
`rapidfuzz`, optional extra `db` = `psycopg[binary]` — once, because ten workers ship into this
one distribution and a dependency added per-worker is a dependency nobody reviews. `canon`,
`anchors` and `contracts` themselves import **only the standard library**; the third-party set
belongs to workers W2, W7 and W8.

Deliberately absent, and required to stay absent: `boto3`/`anthropic`/`strands` (D1, P7),
`datasketch` (MinHash is hand-rolled so the permutation table is a committed versioned artefact
rather than an unpinned seed), any blanket retry helper, and any runtime TOML parser — Python
3.13 ships `tomllib`.
