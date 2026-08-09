<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `evidence/mutation/` — the residual risk, published

This directory holds dated JSON artefacts from the **MUTATION RATCHET**
(`verticals/mainline/packages/mainline-mutation`). Each one is a measurement of
how much of the clause-identity and delta machinery's residual risk was detected
on one seed, on one day, by one build.

`docs/leads/algorithms.md` §8 risk **R-A1** says delta false negatives — a real
weakening that the deterministic lattice classifies as `restate` — are
irreducible, and that this domain will not argue them away. It elects to
**measure** them and publish the number instead. This directory is that
publication.

---

## Read this before quoting a number

**It is a standing measurement and it is never a gate.** Nothing in
`mainline-mutation` blocks a merge, materialises a blocking check or fails a
build on a low figure. `mainline-mutation run` exits `0` whatever the kill rate
is, and the nightly workflow's only numeric assertion is that a *crippled* run
scores worse than an intact one. A number that could stop a merge would acquire
an incentive to be high, and the cheapest way to raise a mutation score is to
delete the mutants the system fails on. This catalogue keeps them:
`comparator_loosening` survives on five of ten fixtures and the operator that
produces it says why, in the source, rather than being tuned away.

**Every proportion is a Wilson lower bound.** Three of three killed is a point
estimate of `1.0` and a 95 % lower bound of `0.438`. Publishing `1.0` there is
not optimism; it is a false statement about how much evidence exists. Point
estimates appear in every artefact beside the bounds, labelled
`point_estimate`, and they are never the claim. The interval is six lines of
arithmetic in `wilson.py` with its preimage written out in the docstring —
deliberately not `statsmodels`, so an opposing expert can check the bound with a
calculator.

**The bounds are bounds over a twelve-clause fixture corpus.** They generalise
to nothing. Twelve authored clauses across four document families cannot support
a claim about a real site's procedure library, and most per-`(class, family)`
cells have one or two trials, where the lower bound is near zero and correctly
so. The figure is a floor on a fixture set, published because a floor on a
fixture set is more than anybody else publishes.

---

## What is in each file

| key | what it is |
|---|---|
| `arm` | `intact` (the production lattice) or `crippled` (a rule switched off) |
| `disabled_lattice_rules` | which rules, when crippled |
| `seed` | the master seed; the whole run is a pure function of it and committed bytes |
| `component_versions` | harness version, catalogue digest, **operator source fingerprint**, identity-policy digest, lattice rule-catalogue fingerprint, and every component version |
| `statements` | the caveats, in full sentences, in the artefact rather than in a README nobody opens |
| `headline.kill` | KILL catalogue: control mutations the pipeline **must** react to |
| `headline.survive` | SURVIVE catalogue: reformats it **must not** react to |
| `per_class`, `per_family`, `per_class_family` | the three breakdowns, each with its own denominator |
| `results` | one row per mutant — the verdict, the witness rule ids, the residue reasons, and the sentence that decided the outcome |
| `skipped` | every class/fixture pairing that produced no trial, with the operator's reason |

There is **no combined "accuracy" figure** anywhere, and adding one would be a
regression. Decision D13: a missed weakening and a manufactured false positive
are different products, and one number hides both.

### The row that matters

`results[]` entries with `"outcome": "survived"` are the named residual risk: a
control mutation that reached the gate undetected. That is the thing to read
first, and the reason one row per mutant is stored rather than a table of class
totals — the interesting question about a kill rate of 0.96 is always *which
four?*

---

## The two arms, and why the second one exists

**PL-2**: a harness that has only ever reported 100 % has not been observed to
assert anything. Every publishing run therefore comes in a pair:

* `mutation-<date>-intact-seed<N>.json` — the production code path, nothing
  disabled;
* `mutation-<date>-crippled-seed<N>.json` — the same catalogue against a lattice
  with rule `R1_DEONTIC` switched off through an injection point that lives in
  the measurement package and **not** in the lattice.

The crippled arm must report a strictly lower bound with `deontic_downgrade`
named among its surviving classes. If it did not, the harness would not be
measuring the lattice at all. The pair is what makes that checkable years later,
and `mutation_run.arm_is_consistent` refuses a row that claims one arm while
carrying the other's rules.

---

## Honest limits, in the artefact and repeated here

* **Path B is never consulted.** `resolve()` is called with no oracle, so the
  published figure is the **model-free floor** and a lower bound on the whole
  system's detection rather than an estimate of it. The harness also records
  what the ABSTENTION RATCHET does with an absent oracle: it treats it as an
  abstention and decision D6 makes an abstention a `weaken`, so a deployment
  that never runs Path B blocks on everything. That is the ratchet failing
  closed as specified, it is recorded on every row as
  `ratchet_delta_without_oracle`, and it is why the outcome is judged on Path A.
* **The adversary is a person.** The `adversarial_paraphrase` cassettes are
  hand-authored. AWS credentials are not valid on the build machine (PL-3) and
  decision D12 keeps the live Bedrock path out of CI, so these are what a
  competent adversary *would* write, not a recording of what one did. Every
  artefact carries the provenance statement verbatim.
* **Residue is a stand-in.** Worker W8 (`margin-assignment`) had not landed when
  this harness was written; `mainline_mutation.residue` derives the five reasons
  from the same authoritative facts and stamps
  `residue_source = "mutation-harness-local/v1"` on every row.
* **CBM is not exercised.** Worker W9's accounting needs a cluster, a commit DAG
  and blame-closure rows. A mutant recorded as `survived` here might still be
  refused at merge by machinery this harness never ran.
* **Cascade S4 is not driven.** Identity recovery is measured over S1/S2/S3
  only, so every `identity_changed` outcome is one a semantic stage might have
  recovered. The preservation bound is conservative in the correct direction.

---

## Reproducing one

No cloud, no credential, no cluster:

```
uv run --package mainline-mutation mainline-mutation run --seed 0 --out evidence/mutation
uv run --package mainline-mutation mainline-mutation run --seed 0 --disable R1_DEONTIC --out evidence/mutation
```

Two runs of one seed produce byte-identical documents apart from
`generated_at`; `tests/e2e/mutation/test_determinism.py` asserts it. A figure
that could not be reproduced from a recorded seed would be an anecdote.

The committed artefacts here were produced by the harness at
`harness_version = mutation/1` with `generated_at` pinned to `2026-08-04T11:00:00+00:00`
so that the two arms in this directory are comparable to each other. Nightly
runs from `.github/workflows/mutation-ratchet.yml` carry their own real
timestamps and are uploaded as workflow artefacts.
