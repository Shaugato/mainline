<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# trappoint-recall

**The substrate half of recall, and the harness that decides whether the rest of it ships.**

Apache-2.0. No database driver, no cloud SDK, no MAINLINE domain vocabulary — so the
arithmetic that settles the product's central empirical bet can be audited by a stranger
with nothing installed but Python.

---

## What is here today

`trappoint_recall.eval` — the evaluation harness. It implements **no retrieval**: no
embedding, no SQL, no vector arm, no model call. That is not an omission. The harness
grades work it did not write, and a harness that shared code with the retriever would
grade its own bugs as passes.

| Module | What it is |
|---|---|
| `measurement.py` | `Measurement` — a point estimate that cannot be separated from its interval, its sample size and its split policy. Wilson for proportions, deterministic bootstrap for means. |
| `splits.py` | The temporally-blocked time wall, enforced by predicates, and the refusal of `AS OF SYSTEM TIME`. |
| `qrels.py` | Graded relevance on the UMBRELA 0-3 scale, with a pydantic model and a committed JSON Schema. |
| `corpus.py` | Retro permits and the routine negative control, loaded together with the split policy that binds them. |
| `backend.py` | `RetrievalBackend` / `ConservingBackend` — the contract an implementation must satisfy to be measured. Plus `NullBackend`. |
| `metrics.py` | Recall@1/@3/@10, Retro-Recall, nDCG@10, MRR, rank distribution, `P@block`, nuisance rate, mean blocking checks, conservation, MI16. |
| `harness.py` | Drives a backend over a corpus; produces one `MetricBundle`. |
| `gates.py` | The five G4-alpha release gates and the vacuity guards. |
| `ablation.py` | The published configuration matrix: channel ladder, cue vs narrative, prefix on/off, 1024-d vs 256-d, beam sweep. |
| `report.py` | Markdown and JSON. There is no rendering path that emits a point estimate alone. |
| `crosscheck.py` | This package's arithmetic checked against scipy and scikit-learn. |
| `cli.py` | `trappoint-recall-eval`. |

The suite that grades against it lives at `tests/eval/recall/`, and its CI lane runner at
`tests/eval/recall/g4alpha_lane.py`.

## The suite is red, deliberately

```console
$ uv run pytest tests/eval/recall -m g4alpha
5 failed
```

MAINLINE's deliverable is a **refusal**. For a product whose output is "no", a test
suite that has never been red asserts nothing: an empty implementation refuses
everything, and a suite that only ever ran green cannot tell that apart from a working
gate. `tests/eval/recall/test_g4alpha_gates.py` is required to fail until a retriever
exists, and it goes green one channel at a time.

Red is only meaningful if green is reachable, so
`tests/eval/recall/test_gate_satisfiability.py` runs a correct oracle against the same
corpus and the same floors and requires it to pass all five. It also runs a backend that
blocks on everything and requires the three noise gates to refuse it — because a
precision gate that cannot fail an indiscriminate blocker is decorative.

## The CI lane

A job that simply failed on red would be broken from the first commit, which is how a
red-before-green discipline gets quietly deleted. So the lane compares the **observed**
colour against the colour this repository **commits to** in
`tests/eval/recall/g4alpha_expected.json`, and fails on the difference:

```console
$ python tests/eval/recall/g4alpha_lane.py --out evidence/recall/g4alpha-lane.json
G4alpha lane: AS_EXPECTED
  observed colour : RED
  expected colour : RED
  outcomes        : failed=5
```

| exit | meaning |
|---|---|
| `0` | observed colour matches the committed expectation — the lane did its job |
| `1` | they differ: the gates regressed, **or** they went green and nobody has flipped the expectation yet. Both need a human |
| `2` | no colour could be determined: a gate was **skipped**, errored in setup, or the marked suite does not match `G4ALPHA_GATE_IDS` |

Exit 2 covers `skipped`, `xfailed` and `xpassed` alike. Marking a release gate `xfail`
converts a refusal into a decoration, and the lane notices that the same way it notices a
skip. The corpus always resolves — `TRAPPOINT_RECALL_CORPUS`, then GS0, then the
committed self-test corpus — so there is no legitimate reason for one of these five tests
not to run.

The expectation **ratchets**. Flipping it to `GREEN` takes a pull request that shows up
in blame; from that commit, any regression fails the lane, and the failure message names
the pre-committed DEMOTE response rather than inviting the file to be edited back.

The artefact records the per-test outcomes, the corpus provenance, and a second,
independent evaluation against the committed default backend (`reference_evaluation`) so
the per-gate reasons are structured rather than scraped from a log. pytest is the
authority on the colour; the reference evaluation is evidence. When the suite is later
pointed at a real retriever the two colours will differ, and that is reported as a fact,
never as a failure.

## The five gates

| Gate | Floor | Companion condition |
|---|---|---|
| `retro_recall_at_3_sev5` | point >= 0.90 **and** Wilson lower bound >= 0.80 | — |
| `p_at_block` | point >= 0.75 on the blinded adjudicated subset | judgement coverage >= 0.90, else undefined |
| `nuisance_rate` | point < 0.03 on the routine-permit replay | a **sensitivity witness**: the policy must block on something in the retro subset |
| `mean_blocking_checks_per_permit` | mean <= 1.0, hard cap 3 probabilistic | **MI16** `bonded_fatalities_all_blocking`, checked against corpus truth |
| `conservation_l3` | `candidates = blocking + advisory + silenced + deduped`, exactly | complete coverage and a non-empty universe |

Floors live in `src/trappoint_recall/eval/data/eval_floors.json` and **ratchet upward
only**. Loosening one requires a pull request that shows up in blame.

### Why three gates carry a companion condition

Two of the four floors and the law are trivially satisfied by a system that does
nothing. A retriever that returns no candidates has a nuisance rate of 0.00, a mean of
0.00 blocking checks per permit, and a conservation law that closes perfectly over zero
candidates. Written naively, three of the five gates would go green on an empty
implementation, and a suite that certifies silence is worse than no suite.

Each companion is taken from the architecture rather than invented: the joint claim
(`P@block` *at* `Retro-Recall@3`), invariant MI16, and the requirement that the
conservation law be checked over something. All three make the gates strictly harder.

## Every number carries its interval

```python
>>> m = retro_recall_at_k(results, qrels, 3, split_policy_id=policy_id)
>>> m.render()
'retro_recall_at_3_sev5 = 0.9167 [0.7500, 0.9772] 95% wilson (n=24, split=TB-2026-01-01-b3bc4c25)'
```

`Measurement` is the only return type of every metric in this package. Inside the code
the interval cannot be dropped by accident; prose has no type system, so
`scripts/recall/no_bare_point_estimates.py` fails the build when a recall metric appears
in `docs/`, the README or the deck without one. The two controls are independent on
purpose: one makes the honest thing easy, the other makes the dishonest thing fail.

Interval methods are stated, never assumed. Wilson score intervals are correct for
binomial proportions and nothing else, so `Retro-Recall@k`, `P@block` and the nuisance
rate get Wilson; `nDCG@10`, `MRR` and mean blocking checks per permit are means of
per-query quantities and get a deterministic bootstrap percentile interval. Applying
Wilson to a mean would be a category error dressed up as rigour.

## The time wall

Retro-Recall is only meaningful if nothing the retriever can see post-dates *t*. Three
predicates, all required:

```
occurred_at   < t
ingested_at   < t
corpus_commit <= t
```

`AS OF SYSTEM TIME` is **refused**, not discouraged. CockroachDB's default
`gc.ttlseconds` is 4 hours, so an AOST query aimed months back either errors or, in a
configuration where the horizon was extended just enough, silently evaluates over a
window nobody intended. `splits.refuse_as_of_system_time()` and
`splits.assert_no_as_of_system_time(sql)` make that mistake impossible to make quietly.

Random splits are refused for the same reason in a different direction: a random split
over an incident corpus leaks the future through vocabulary drift, equipment model names
and investigator style.

## Command line

```console
$ trappoint-recall-eval gates --corpus tests/eval/recall/fixtures/harness_selftest
$ trappoint-recall-eval gates --corpus <dir> --backend mypkg.backends:MyBackend --format json --out status.json
$ trappoint-recall-eval ablation --corpus <dir> --factory mypkg.backends:make --out ablation.md
$ trappoint-recall-eval floors
$ trappoint-recall-eval schema --out qrels-v1.schema.json
$ trappoint-recall-eval selfcheck
```

Exit codes are the interface: `0` every gate passed, `1` at least one gate is RED, `2`
the harness could not run. A lane that treats RED and "could not run" the same way goes
green when the corpus disappears.

## Implementing a backend

```python
class MyBackend:
    name = "arms-v1"

    async def retrieve(self, query: EvalQuery, k: int) -> list[ScoredCandidate]:
        ...

    async def declared_tally(self, query: EvalQuery) -> RunTally:
        ...   # the counters mainline_meas.recall_run would carry
```

`declared_tally` is optional to the type system and mandatory in practice: the
conservation law compares the *declared* counters against *independently enumerated*
candidates, which is only a real check if the two come from different places. A backend
that publishes no counters makes the law unverifiable, and unverifiable is a failure,
not a pass.

Two things the harness will not take your word for:

* **which severity-5 events were bonded to the permit** — that is corpus ground truth,
  and MI16 is checked against it. Projections are enforced, never trusted.
* **the time wall** — a backend must honour it internally. The harness cannot enforce a
  predicate inside code it did not write, and every report says so rather than implying
  otherwise.

## Corpus format

```
<dir>/manifest.json    name, preliminary, synthetic, provenance
<dir>/queries.jsonl    one permit per line: retro (with a truth precursor and a wall)
                       or routine (the negative control)
<dir>/qrels.jsonl      one UMBRELA judgement per line
<dir>/split.json       {wall, corpus_commit, kind, note}
```

`split.json` is mandatory. A recall number with no split policy is a number without an
experiment.

The suite ships `tests/eval/recall/fixtures/harness_selftest/` — synthetic, committed,
regenerable by `tests/eval/recall/fixtures/generate.py`, and stamped SYNTHETIC and
PRELIMINARY on every report it produces. It is **not a gold set**. It exists so the
G4-alpha assertions are executable before GS0 lands, and it is sized so that a correct
retriever passes (24 severity-5 retro permits gives a Wilson lower bound of 0.862 at
perfect recall) and a silent one fails. Point the lane at a real corpus with
`TRAPPOINT_RECALL_CORPUS=<dir>`, or drop GS0 at `tests/fixtures/recall/gs0/` and it is
picked up automatically.

## What this package does not claim

* **No customer-grade floor is claimed at G4-alpha.** The claim is the harness, the
  arithmetic and the refusal — not the score.
* **Proof of Exhausted Recall establishes that every candidate the retrieval returned
  and scored below theta is accounted for, that the score-sorted set was not hand-edited,
  and that tau was fixed before the run under an anchored policy. It does not prove
  exhaustion of the corpus: C-SPANN is approximate and its trees mutate on every insert.**
* **No bit-identical ANN replay exists.** The candidate set is persisted with scores
  rather than promising replay of the search. *Unverified.*
* **The harness has not been run against a live CockroachDB cluster or a live Bedrock
  endpoint.** It does not need one, and nothing in this package requires a cloud
  credential to be considered done. Latency and index-use claims belong to
  `recall-ann-arms-explain`, not here.

## Licence

Apache-2.0. Per-file REUSE SPDX headers; see `LICENSES/` at the repository root.
