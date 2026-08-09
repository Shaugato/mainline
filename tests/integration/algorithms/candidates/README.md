<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Candidate cascade — integration suite (worker W7, `candidate-cascade`)

What a green run here entitles you to say, and what it does not.

## Status — the cluster-backed half HAS now been run, and it was green

**2026-08-09.** All **31** tests in this directory passed against a live
**CockroachDB CCL v26.2.5** (cluster version 26.2, `feature.vector_index.enabled
= true`), single node, in Docker on the build machine. Nothing skipped.
Reproduced on **two independently started nodes** — a throwaway in-memory one
brought up for the run, and a separate long-running node already on the machine
— so the result is not an artefact of one container's state.

That retires the four ❌ claims listed further down — they are now measured, on
this version, on this machine. It retires nothing about **CockroachDB Cloud**,
which is a different tier with different statistics and remains unmeasured from
here; §F1 of `docs/leads/algorithms.md` records that an *unhinted* arm on Cloud
Basic at ~5,200 rows did not use the index, and the reason every arm this
package generates pins `@ce_ann` is that finding, not this one.

A dated paragraph in a README is not evidence. Re-run it (recipe below) before
repeating the claim; the suite is deterministic and takes about two minutes.

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

### Bringing a cluster up by hand, and the trap in the way

⚠ **The image's entrypoint refuses `--listen-addr=0.0.0.0`.** On
`cockroachdb/cockroach:v26.2.5` the `cockroach.sh` wrapper that is the image's
default `ENTRYPOINT` validates the flag and exits 1 before the server starts:

```
error: hostname of listen_addr must be "127.0.0.1" or "localhost"
```

Binding to loopback *inside* the container is not a workaround, because then a
published port has nothing to forward to. Bypass the wrapper and run the binary:

```bash
docker run -d --name mainline-w7-crdb \
  -p 127.0.0.1:26299:26257 -p 127.0.0.1:18099:8080 \
  --entrypoint /cockroach/cockroach \
  cockroachdb/cockroach:v26.2.5 \
  start-single-node --insecure \
    --listen-addr=0.0.0.0:26257 --http-addr=0.0.0.0:8080 \
    --store=type=mem,size=1GiB

MAINLINE_TEST_DSN='postgresql://root@127.0.0.1:26299/defaultdb?sslmode=disable' \
  pytest tests/integration/algorithms/candidates -q

docker rm -f mainline-w7-crdb
```

Non-default host ports are used on purpose: 8080 is frequently already taken on
a developer machine, and a port clash reads as "the cluster is broken".

This is the recipe the 2026-08-09 run above used. It is **not** a fix for
`compose.yaml` or `.github/workflows/db.yml`, both of which pass
`--listen-addr=0.0.0.0` through the default entrypoint and are therefore subject
to the same refusal; those files belong to other workers and are flagged, not
edited, from here.

## What a green-with-skips run does NOT entitle anyone to claim

A run in which the cluster-backed half **skipped** proves none of the following.
All four were measured green on 2026-08-09 against local v26.2.5 — a *skipped*
run does not inherit that, and neither does CockroachDB Cloud.

- ❌ that `ARM_SQL` plans as a prefix-constrained `vector search` on CockroachDB
- ❌ that the `UNION ALL` band probe and the reference `InMemoryBandIndex` agree
- ❌ that `trigram.similarity` equals the cluster's `similarity()`
- ❌ that `word_similarity` / `strict_word_similarity` / the `<->` trigram family
  really are absent (the suite pins that absence, but only when it can run)

Their current status is recorded under `unverified:` in
`verticals/mainline/packages/mainline-domain/novelty/minhash-band.yaml`, which is
the file to read rather than this one if the two ever disagree.

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
