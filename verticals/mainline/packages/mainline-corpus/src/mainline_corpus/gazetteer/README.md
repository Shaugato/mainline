<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# `mainline_corpus.gazetteer` — the hand-written vocabulary of the synthetic world

Every string in this directory is **written by hand**. Nothing here is sampled, generated,
model-authored or scraped. That is not a stylistic preference; it is the reason the directory
exists.

## Why hand-written

The anchor extractor that MAINLINE runs over clause text and incident narratives
(`mainline_domain.anchors`) is a `pyahocorasick` automaton built over a gazetteer of the same
shape: equipment codes, citation bodies, setpoint units, isolation vocabulary. An anchor is an
*identity* constraint — two clauses whose identity anchors conflict are not the same clause, and
a conflicting anchor is a refusal, not a down-weight.

If the corpus generator invented asset tags or citations from a random provider, the automaton
would find nothing, every anchor set would be empty, every identity comparison would fall through
to fuzzy text, and the corpus would silently stop testing the thing it exists to test. The
failure would be invisible: green tests, empty anchors.

So: **the corpus draws its literals from this directory, and only from this directory.** The
generator may choose *which* hand-written literal to use (from a named RNG stream), never *what
the literal is*.

## Relationship to `mainline_domain`'s gazetteer

They are different objects and both are needed.

| | `mainline_domain/data/gazetteer/*.toml` | `mainline_corpus/gazetteer/*.yaml` (this directory) |
|---|---|---|
| Owns | the **shapes** — which two-letter equipment codes exist, which citation bodies exist, which units are setpoint units | the **instances** — the actual tags, standards, control classes and setpoints of one fictional operator |
| Ships in | the product | the corpus generator only |
| Licence | FSL-1.1-ALv2 | FSL-1.1-ALv2 |

The collision was **measured against the shipped extractor**, not assumed. Every asset tag in
`assets.yaml` carries an explicit hyphen, which is what `extract.py` requires for a code it does
not know ("unknown prefixes fail closed"), so all 180 tags are claimed as `EQUIPMENT_TAG` or
`INSTRUMENT_LOOP` today. Isolation point ids are written `LOP-41041`, not `LOP-4104-01`, because
the shipped isolation regex rejects the second form. Citations in `citations.yaml` were each run
through `iter_anchors` before being written down.

Two gaps in the *product* gazetteer were found while doing this and are recorded here rather
than patched, because `mainline_domain` belongs to the algorithms lead:

1. `setpoint-units.toml` has `degC` but not `°C`, and `canonicalise` does not fold the degree
   sign. `150 °C` — the literal text of the spine clause — extracts **no setpoint anchor**.
   `setpoints.yaml` therefore records both `unit_display` (`°C`, what a document says) and
   `unit_token` (`degC`, what the extractor can currently see).
2. The setpoint unit alternation is built in file order rather than longest-first, so `11.2 mm/s`
   is claimed as `11.2mm`. `mm/s` is also absent from the unit list.

Neither is this worker's file to change; both are reported upstream.

## Files

| File | Contents |
|---|---|
| `sites.yaml` | The four Kestrel Resources sites, their codes, timezones, and relative event weight. |
| `taxonomy.yaml` | The frozen level-1 ICMM-MUE-anchored activity vocabulary (16 fonds) and the level-2 / level-3 label banks beneath it. |
| `assets.yaml` | Every asset family, every hand-written member tag, and the derivation rules for companion tags (motor, instrument, accumulator). Also the anchored energy edges and the deliberate under-declaration path. |
| `hazard_energies.yaml` | The eight closed `control_failure.hazard_energy` values, with the media that carry them. |
| `control_classes.yaml` | The control-class vocabulary — the join key between `control_failure` and a clause's Control Assertion Tuple. |
| `setpoints.yaml` | Setpoint parameters, units, admissible values, and which direction of change is a *strengthening*. Includes the spine's seal-face alarm. |
| `citations.yaml` | Concrete regulatory and standards citations, bound to the MUE class they govern. |
| `people.yaml` | Given-name and surname pools, orgs, role→rank table, and the anchored people (including D. Okonjo). |
| `documents.yaml` | The 36 controlled documents across five code families, with their revision cadence class. |
| `anchors.yaml` | The dated structural spine — the external references, dates, sites and assets that the film hangs off. Prose is *not* here; the authored fixtures own the prose. |
| `phrases.yaml` | Era-banded vocabulary (2004→2026) and the deterministic title templates. This is what makes the vocabulary-drift injector a real lexical drift rather than a claim. |

## Rules for editing

1. **Never delete a literal that `anchors.yaml` references.** The loader raises if an anchor
   points at a tag, document or person that no longer exists; that is a build failure, not a
   warning.
2. **Adding a literal is safe; reordering one is not.** The generator indexes into these lists
   from a seeded stream, so reordering `people.yaml`'s surname pool changes every person in the
   corpus and invalidates every committed render-cache entry. Append, do not insert.
3. **No prose.** A sentence a human would read on camera belongs in
   `verticals/mainline/fixtures/corpus/authored/`, which is hand-authored verbatim and is
   cross-checked against the VO by `test_camera_strings_agree`. A fifth copy of the 2013 commit
   message living here would be a fifth thing that can drift.
4. **`hazard_energies.yaml` is closed.** Its eight values are a `CHECK` constraint in
   `ARCHITECTURE.md` §5.4. Adding a ninth is a migration, not a data edit.
