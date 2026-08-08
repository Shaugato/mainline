<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Candidate cascade — integration suite (worker W7, `candidate-cascade`)

What a green run here entitles you to say, and what it does not.

## The suite is in two halves and they prove different things

| Half | Needs a cluster | Runs in CI today | Proves |
|---|---|---|---|
| `test_corpus_doubling.py` (all but the last test) | no | **yes** | the cascade's *work* grows sublinearly as the corpus doubles, measured as a deterministic count of rescored pairs |
| `test_band_probe_sql.py`, `test_arm_explain_live.py`, `test_similarity_matches_cluster.py`, `test_corpus_doubling.py::test_band_probe_latency_grows_sublinearly` | **yes** | only where one is reachable | the statements this package generates really plan and really return what the reference implementation returns |

## Running it

```
# offline half only — no setup at all
pytest tests/integration/algorithms/candidates

# with a cluster (either form)
MAINLINE_TEST_DSN=postgresql://root@localhost:26257/defaultdb?sslmode=disable \
  pytest tests/integration/algorithms/candidates
#   ... or just put a `cockroach` binary on PATH and the suite starts a
#   single in-memory node for the session and shuts it down after.
```

Docker is deliberately not orchestrated here — the recall lead's index-truth
suite already does that well, and a second copy would be a second thing to keep
working. If neither source is available every cluster-backed test **skips with a
message naming what was missing**.

## What a green-with-skips run does NOT entitle anyone to claim

- ❌ that `ARM_SQL` plans as a prefix-constrained `vector search` on CockroachDB
- ❌ that the `UNION ALL` band probe and the reference `InMemoryBandIndex` agree
- ❌ that `trigram.similarity` equals the cluster's `similarity()`
- ❌ that `word_similarity` / `strict_word_similarity` / the `<->` trigram family
  really are absent (the suite pins that absence, but only when it can run)

Those four are listed under `unverified:` in
`verticals/mainline/packages/mainline-domain/novelty/minhash-band.yaml` and they
stay there until this suite has run green against a real CockroachDB v26.2.

## What it DOES entitle anyone to claim, today, with no cluster

- the MinHash signature is byte-identical across interpreter processes with
  different `PYTHONHASHSEED` values (`tests/unit/domain/candidates/test_minhash_determinism.py`)
- the committed permutation table re-derives from its published recipe, and a
  one-digit edit — even one whose digest has been recomputed — is refused
- band recall on a seeded labelled corpus tracks the analytic S-curve across
  seven Jaccard buckets, with the transition at the knee 16 × 8 actually puts it
  at (0.7071), not at a rounded value
- the cascade rescores 1.6× as many pairs for an 8× corpus, and work per clause
  falls at every doubling
- the plan assertion refuses in four independent ways against committed plan text

## The fixture DDL is a mirror, not the migration

`_w7_support.py` creates a *minimal* `mainline.clause_band` /
`mainline.clause_embedding` / `mainline.clause_version` inside a throwaway
database. The real migrations live in `verticals/mainline/db/migrations/` and
belong to the datamodel lead. Two differences are deliberate and are stated in
that file's docstring: the embedding column is `VECTOR(8)` rather than
`VECTOR(1024)` (nothing under test depends on the dimension), and the tables
live in a per-test database so the production-shaped identifiers in the
package's statements resolve unchanged without ever touching a shared
`mainline` schema.
