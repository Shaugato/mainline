<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-mutation` — MUTATION RATCHET

**Two catalogues, one harness, and a number that is allowed to be bad.**

`docs/leads/algorithms.md` §8 risk **R-A1** says delta false negatives — a real
weakening that the nine-rule lattice classifies as `restate` — are irreducible,
and declines to argue them away. It elects to *measure* them, per mutation class,
with Wilson lower bounds, and to publish the result as a standing metric rather
than as a launch claim. This package is that measurement.

```
uv run --package mainline-mutation mainline-mutation run --seed 0 --out evidence/mutation
uv run --package mainline-mutation mainline-mutation run --seed 0 --disable R1_DEONTIC --out evidence/mutation
uv run --package mainline-mutation mainline-mutation catalogue
```

```python
from mainline_mutation import run, build_report, surviving_classes

intact = run(seed=0)
build_report(intact)["headline"]["kill"]["wilson_lower"]   # the claim
surviving_classes(intact.results)                          # the residual risk, named
```

---

## It measures. It does not gate.

Nothing here blocks a merge, materialises a `blocking_check`, or fails a build
on a low figure. The CLI exits `0` whatever the kill rate is. The nightly
workflow's only numeric assertion is that a *crippled* arm scores worse than an
intact one — an assertion that the harness is measuring something, not that what
it measures is good.

That is not modesty. A number that can fail a build acquires an incentive to be
high, and the cheapest way to raise a mutation score is to delete the mutants the
system fails on. This catalogue keeps them: `comparator_loosening` survives on
five of ten fixtures, and the operator that produces it explains why in its own
docstring rather than being tuned out.

## Two catalogues, never averaged (decision D13)

| | what it is | failure |
|---|---|---|
| **KILL** (16 classes) | control mutations the pipeline **must** react to — a `weaken`/`remove` verdict or a residue row | a **missed weakening**: a fatality the gate let through |
| **SURVIVE** (12 classes) | identity-preserving reformats it **must not** react to | a **manufactured false positive**: enough of them breach the nuisance ceiling that R-A7 says gets a rule *rejected, not tuned* |

There is no combined "accuracy" figure anywhere in this package and adding one
would be a regression. The two failure directions are different products and one
number hides both.

## Every proportion is a Wilson lower bound

Three of three killed is a point estimate of `1.0` and a 95 % lower bound of
`0.438`. Publishing `1.0` there is not optimism; it is a false statement about
how much evidence exists. `wilson.py` implements the interval directly, in six
lines, with the preimage written out in the docstring — deliberately not
`statsmodels`, because a bound whose derivation nobody in the room can check by
hand does not survive cross-examination.

## The harness has been red (PL-2)

`tests/e2e/mutation/test_red_first.py` runs the whole catalogue against a
lattice with rule `R1_DEONTIC` switched off and asserts that the kill rate falls
with `deontic_downgrade` named as a surviving class. The injection point lives
in `lattice_injection.py`, in *this* package: nothing in
`mainline_domain.lattice` knows it exists. A `disabled_rules` argument threaded
into the real lattice would be a switch reachable from a gate path, and a gate
whose rules can be turned off by an argument is not a gate.

With nothing disabled, `explain_with` **delegates** to
`mainline_domain.lattice.explain`, so the intact arm of every published run is
the production code path and nothing else. `test_injection.py` asserts that
agreement over forty fixture pairs rather than assuming it.

## The salami classes are the interesting ones

`salami_5`/`_10`/`_20` walk the comparator through the two cells rule `R3` is
**deliberately silent** on (`<=` ↔ `=`, documented in `lattice/rules.py` as the
commonest restatement in a real library), moving the magnitude on the step where
the comparator *family* changes — because `R2` stays silent then, on the grounds
that comparing a bound against an exact value is arithmetic on two different
assertions.

The result is decision **D7** demonstrated on data: every adjacent diff is
`restate`, the diff against the **origin** is `weaken`. The runner records
`chain_adjacent_max_force` on every multi-step row, so the artefact states that
as a measurement. A salami whose adjacent steps were individually detectable
would prove nothing about ORIGINDIFF, and the recorded number is what
distinguishes the two cases.

## Layout

```
wilson.py             the interval, and the rule that only the LOWER bound is published
model.py              the frozen types and the closed six-member outcome vocabulary
resources.py          committed data files and `catalogue_sha256()`
catalogue.py          binds the declaration to the operators; `operator_fingerprint()`
fixtures.py           the twelve historical revisions, validated on load
directrix.py          one registry, built from the committed seed through the real loader
operators/kill.py     16 control mutations, each coupled to the committed lexicon
operators/survive.py  12 reformats, eleven of which must leave `canon_sha256` alone
paraphrase.py         committed cassettes; no model is reached, here or anywhere
lattice_injection.py  the crippled arm (PL-2)
pipeline.py           canon -> anchors -> CAT -> lattice -> cascade, all real code
residue.py            a STAND-IN for worker W8, named on every row
judge.py              facts -> one of six outcomes, in one file so it can be disagreed with
metrics.py            per class, per family, per cell, and two headline figures
runner.py             deterministic given a seed; records every skip
report.py             the dated JSON artefact, with its caveats inside it
sql.py                `mainline_meas.mutation_run` / `mutation_result`, driver-free
cli.py                `mainline-mutation run|catalogue`
```

## What this does NOT measure, stated where it will be read

* **Path B is never consulted.** The published figure is the model-free floor and
  a lower bound on the whole system's detection. The harness also records that
  `resolve(path_a, oracle=None, theta)` returns `weaken` for *every* pair —
  an absent oracle is an abstaining one and D6 makes an abstention a weakening —
  so a deployment that never runs Path B blocks on everything. That is the
  ratchet failing closed as specified, it is why the outcome is judged on Path A,
  and it travels on every row as `ratchet_delta_without_oracle`.
* **The adversary is a person.** The paraphrase cassettes are hand-authored
  (PL-3, D12). No model was called. Every artefact says so in a field.
* **Residue is a stand-in** for worker W8, named on every row.
* **CBM (worker W9) is not exercised**, and **cascade S4 is not driven**.
* **Twelve fixtures generalise to nothing.** The bounds are bounds over this
  corpus.
* **A measured coverage gap, found by this harness**: the CAT extractor can
  produce 60 parameter keys, DIRECTRIX ratifies 74, and the intersection is 6.
  Every other parameter abstains and fails closed to `weaken` (R-A4 working as
  designed). The intersection is recomputed on every run and printed into the
  artefact as `directrix_ratified_and_extractable`, so the number cannot rot into
  a comment.

The full list is `novelty/mutation-ratchet.yaml` under `unverified:`, which is
validated by `tests/unit/domain/novelty/test_novelty_manifest.py`.

## Where the SQL lives

`mainline_meas.mutation_run` (`0049y`) and `mainline_meas.mutation_result`
(`0049z`), welded append-only by `0149y`/`0149z` onto the substrate's own
`mainline.fn_refuse_mutation()`.

**Not `0209`.** The worker brief names `0209_meas_mutation.sql`; the migration
reconciliation ruling of 2026-08-08 revokes the `0200-0219` annexe, marks `0200`
and above UNALLOCATED, and makes `trappoint migrate lint` rule B refuse any file
that claims a number no band grants. `docs/leads/algorithms.md` names these
objects among the ones that "take their numbers from the three bands above when
they are written". `test_sql_shape.py::test_no_file_of_this_worker_claims_an_unallocated_number`
holds it.
