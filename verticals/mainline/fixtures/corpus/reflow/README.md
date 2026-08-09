<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The reflow tree — what the 2016 retypeset did, measured

## Why this directory exists

`injector_retypeset.jsonl`, in the answer-key tree next door, has 624 rows and every one of them
carries `"identity_held": true`.

That boolean is a constant the generator wrote. It is not wrong — but it is not *evidence*
either, and in a repository whose first principle is that **a projection is enforced, never
trusted** (P2), a survival claim carried by a field the claimant filled in is exactly the defect
class the product exists to punish. It looks right, and it was never derived from anything.

This tree replaces that one boolean with three things a reader can check without trusting us.

**A re-derivation.** Every clause's `clause_uuid` is recomputed here, from the natural key the
clause was *born* at — `uuid5(CORPUS_NS, "clause:<site>/<doc>/<birth label>")` — and compared to
the identity the record carries. A reflow that minted a fresh identity on the post-2016 side
fails check `R03`.

**A refutation.** The same mint is applied to the address the clause prints under *after* the
reflow. Where the label moved — which is all 624 of them — that value must **not** equal the
clause's identity. This is the falsifiable half: if identity were a function of the printed
label, a retypeset would destroy it, and the corpus's whole claim would be circular. Check `R04`.

**A scoreboard.** Four registers are run over the reflow boundary and scored. That is the
headline below, and it is the sentence beat 1 says out loud.

---

## The headline

> Across one retypeset of **24** controlled documents, a register keyed on the printed clause
> number recovers **0 of 624** obligations. A register keyed on the identity the document
> carries recovers **624**.

| register | true positive | false merge | false split | ambiguous | precision | recall |
|---|---:|---:|---:|---:|---:|---:|
| `printed_label` | 0 | 0 | 624 | 0 | — | 0.000 |
| `ordinal` | 26 | **598** | 0 | 0 | 0.042 | 0.042 |
| `control_class` | 8 | 0 | 0 | 616 | 1.000 | 0.013 |
| `clause_uuid` *(control)* | 624 | 0 | 0 | 0 | 1.000 | 1.000 |

The `ordinal` row is the one to read twice. A register that walks paragraphs in order does not
merely lose obligations — it **misattributes 598 of them**, confidently and silently. Every
precursor those clauses carried is now hanging off the wrong obligation, and nothing in the
document says so. That is the failure the merge gate exists to make impossible, and
`reflow_collision.jsonl` names all 598 of them one at a time.

`control_class` is the closest offline stand-in for a semantic matcher. It never gets an answer
*wrong* — but it can only decide 8 cases out of 624, because a document has several clauses of
the same control class and the key cannot separate them. An undecided link is an unwalked
ancestry.

### What these numbers do not say

Reproduced verbatim from `reflow_scoreboard.json`'s own `must_not_claim` field, which is emitted
into the file so a number lifted out of it cannot travel without its caveat:

- This stage does **not** measure MAINLINE's clause linker. It measures what a register keyed on
  a printed label, an ordinal or a control class loses when a document is retypeset.
- The `clause_uuid` register scores 1.000 **by construction**: the corpus carries that identity
  across the reflow, so a register keyed on it cannot miss. It is a control, not evidence.
- The corpus is **synthetic**. These numbers bound a label-keyed register from above on a world
  built to be legible; a real fonds is messier, and the losses would be larger.
- **No clause text is compared anywhere in this stage.** A real content-similarity register would
  score between `control_class` and `clause_uuid`, and is not measured here.

---

## Was the reflow real? (decision D6)

D6 says the 2016 retypeset is *a genuinely different second template — different numbering
scheme, different style set, different clause ordering — not a string substitution*. Three
independent statistics test that, per document, in `reflow_document.jsonl`.

| statistic | what a *renumbering* would score | measured |
|---|---|---|
| label-change fraction | < 1.0 (only the affected range moves) | **1.000** in all 24 |
| shared label grammars | ≥ 1 (same address form, new numbers) | **0** in all 24 |
| Kendall tau distance | **0.000** (relative order preserved) | min 0.286, mean 0.390, max 0.562 |

Kendall tau distance is the fraction of clause pairs whose *relative order* the reflow inverted.
A uniformly random permutation scores 0.5 in expectation. Measuring 0.390 across the whole
retypeset says the two schemes disagree about the document's structure nearly as much as chance
would — which is what "a chapter per control class" versus "the order the work is done" means
when it is written as a number.

The label grammars are disjoint because generation 1 addresses a clause as `N.N` or `N.N.N(x)`
and generation 2 addresses it as `N.N.N`. Two schemes that share no address *form* cannot be one
scheme with different numbers in it.

---

## Beat 1's exhibit

`spine_reflow.json`, in full prose:

> `PRO-MEC-014` clause **7.3** became clause **5.2.1** on 2016-11-21, and moved from position 25
> to position 29 of its document. Its identity, `2ad35fa5-d174-5eb1-8550-05adfa90e08d`, is the
> mint of the natural key it was born at in 2011, and it is **not** the mint of the address it
> prints under today (`25b02b30-a69a-5022-b54a-91494379efbd`, recorded in the file as
> `would_be_identity_if_label_derived`). Identity is anchored where the obligation came from, not
> where it currently sits on the page.

Both labels are checked against `gazetteer/anchors.yaml` (`clause_label_2011`,
`clause_label_2016`) rather than restated here, so the film cannot quote a number the corpus does
not contain. Check `R13`.

---

## Red before green (PL-2)

`verify.py` and the generator it audits live in the same package and were written by the same
hand. Fourteen green checks in that situation are not evidence — they are a coincidence nobody
has tested. So **every build breaks the corpus on purpose, five ways**, and asserts that the
audit notices. `reflow_nemesis.json` is the record.

| id | the defect | must turn red | actually turned red |
|---|---|---|---|
| `N1` | identity minted from the post-reflow printed label | `R04` | `R04` |
| `N2` | a "retypeset" that reuses the old addresses | `R05` `R06` `R10` | `R04` `R05` `R06` `R09` `R10` `R13` |
| `N3` | labels change, positions do not — a renumbering | `R07` `R08` | `R07` `R08` `R09` `R11` |
| `N4` | the injector's `identity_held` copied into this tree | `R14` | `R14` |
| `N5` | every register scored against itself | `R10` `R11` | nine checks, including both |

**5 killed, 0 survived.** A survivor would exit `3`, which ranks above a failing check (`1`),
because a failing check is the audit working and a surviving mutation is the audit not working.

---

## The files

| file | rows | what it is |
|---|---:|---|
| `reflow_pair.jsonl` | 624 | one clause, both sides of the reflow, identity re-derived and refuted |
| `reflow_document.jsonl` | 24 | one document: displacement statistics and the reflow verdict |
| `reflow_collision.jsonl` | 1838 | every wrong or undecidable match the four registers proposed |
| `reflow_scoreboard.json` | — | the table above, with `must_not_claim` attached |
| `spine_reflow.json` | — | beat 1's exhibit |
| `reflow_thresholds.json` | — | the floors enforced, and the values measured when they were chosen |
| `reflow_nemesis.json` | — | the five self-refutations and their outcomes |
| `verify_report.json` | — | all fourteen checks, each with its reason and its numbers |
| `index.json` | — | digests for every file above; written last |

**Nothing here loads into a `mainline.*` table.** Every `TableSpec` this stage declares carries
`table: null`, and `index.json` records `loads_into_database: false` with the reason. The
retypeset's effect on the schema is already carried by `clause_version.printed_label` and
`clause_version.ordinal`, written from the answer key. This tree is *evidence about* the corpus,
not more corpus — and a loader that grew a habit of importing whatever JSONL it found would
import none of it.

---

## Reproducing it

```
# from verticals/mainline/packages/mainline-corpus/src
python -m mainline_corpus.reflow --answer-key ../../../fixtures/corpus/answer-key

# or, without writing anything: rebuild into a temp dir and compare every byte
python -m mainline_corpus.reflow --check
```

The world is **rebuilt in memory** from `mainline_corpus.blame.build` every time.
`--answer-key` is a *cross-check*, never a source: the rebuilt retypeset schedule must agree with
the committed `injector_retypeset.jsonl` row for row, and a mismatch is a refusal naming the
difference. A stage whose whole claim is *"this survival was derived, not asserted"* cannot take
its inputs from a directory it did not produce and still call the derivation independent.

No clock, no network, no database, no randomness, no model. Two runs are byte-identical, which
`--check` is the command for.

Exit codes: `0` clean · `1` a check failed · `2` the committed tree drifted from a fresh build ·
`3` a deliberate defect survived the audit.
