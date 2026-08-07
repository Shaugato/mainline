<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: FSL-1.1-ALv2 -->

# `recall_index` — the three-layer proof that the vector index was actually used

The claim this suite exists to support is narrow and load-bearing:

> The archival taxonomy **is** the vector-index prefix. Each arm of Channel C binds every
> prefix column to a specific value, so each arm searches exactly the K-means tree belonging
> to one ancestor at one archival level — and that is what makes ancestry-scoped retrieval
> possible at all. Without it there is no diachronic recall, only similarity search with extra
> steps.

An unused index here is not a performance regression. C-SPANN maintains a **separate K-means
tree per distinct prefix value**, so the prefix does not filter a result set — it *selects the
tree that is searched*. A cue that ends up outside the searched tree is not ranked lower; it is
unreachable, by every arm, with no error anywhere and no row anywhere that is wrong. That is
why the proof has three independent layers and why none of them substitutes for another.

## The layers

| # | Module | Needs | Proves |
|---|---|---|---|
| 0 | `test_ix00_arm_shape.py` | nothing | The generator emits ≤16 fully-literal-bound arms plus the sweep; the cap bites and records every dropped arm; the statement fits the public endpoint's envelope **with measured headroom**. |
| 1a | `test_ix01_plan_parser.py` | nothing | The plan assertion has teeth: four bad fixtures each fail for their **own** reason, and the digest is stable against statistics and sensitive to the index. |
| 1b | `test_ix02_plan_pgwire.py` | a cluster | Every generated arm really does plan as a constrained `vector search` on this CockroachDB — plus the negative controls, which must fail. |
| 1c | `test_ix03_plan_mcp.py` | a cluster + an MCP key | The same assertion over **CockroachDB's own public endpoint**, one arm per call. |
| 2 | `test_ix04_sublinearity.py` | a cluster | `t(2n)/t(n) < 1.7` per arm across 5k → 10k → 20k, a planted precursor in top-k, and a forced-scan control proving the measurement can tell the two apart. |
| 3 | `test_ix05_tuple_in_characterisation.py` | a cluster | What the **not-shipped** tuple-`IN` form does either side of the runtime value of `optimizer_span_limit`. Expected to drift; drifting is the point. |
| — | `test_ix06_ingest_degradation.py` | a cluster | The measured batch threshold, replacing an invented one. |

Layers 0 and 1a **never skip**. That is deliberate: the part of the proof that is about *our*
generator and *our* assertion is always green or always red, and only the part that is about
*CockroachDB* depends on there being a CockroachDB.

## Running it

```bash
# Everything that needs no cluster (always runs, anywhere):
pytest tests/integration/recall_index -m shape

# The full plan and behaviour lanes against a local single node:
MAINLINE_TEST_DSN='postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable' \
  pytest tests/integration/recall_index -s

# Over CockroachDB's public endpoint as well:
MAINLINE_MCP_TOKEN=... MAINLINE_MCP_CLUSTER_ID=... pytest tests/integration/recall_index -m mcp -s

# The nightly lanes:
pytest tests/integration/recall_index -m nightly -s
```

A cluster is found in this order and the suite **skips with a reason** if none is available:
`MAINLINE_TEST_DSN` / `COCKROACH_URL` / `CRDB_URL` → a `cockroach` binary on `PATH` → a running
Docker daemon.

### Knobs

| Variable | Default | What it changes |
|---|---|---|
| `MAINLINE_RECALL_INDEX_SIZES` | `5000,10000,20000` | The doubling sequence for layer 2. |
| `MAINLINE_RECALL_INDEX_REPEATS` | `10` | Executions per run. |
| `MAINLINE_RECALL_INDEX_RUNS` | `3` | Runs medianed per point. |
| `MAINLINE_RECALL_INDEX_PLAN_ROWS` | `5000` | Corpus size the plan lane grows to first. |
| `MAINLINE_RECALL_INDEX_TUPLEIN_ROWS` | `5000` | The characterisation fixture. |
| `MAINLINE_RECALL_INDEX_INGEST_ROWS` | `1000` | Rows per batch-size probe in the ingest curve. |

## What a green run does and does not entitle anybody to claim

**Does:** that on the cluster that ran it, every generated arm planned as a prefix-constrained
vector search on the named index with non-empty prefix spans and no full scan; that arm latency
grew sublinearly across two doublings; that a planted precursor was retrieved; and — when the
MCP lane ran — that CockroachDB's own endpoint said the same thing.

**Does not:** that the search was exhaustive. C-SPANN is approximate and its trees mutate on
every insert, so there is **no bit-identical replay of an ANN result**. The candidate set is
persisted with its scores rather than the search being promised replayable, and
`recall_run.index_plan_digest` and `index_generation` exist precisely because the structure
that was searched can change underneath a receipt.

**And a run with skips claims nothing about the skipped layer.** The skip messages say which
of the three cluster sources was missing.

## Artefacts

* `artefacts/index_plan_digest.txt` — the digest a `recall_run` row would carry for this arm
  set on this cluster (written by IX-02).
* `artefacts/sublinearity.json` — every per-arm curve and ratio (written by IX-04).
* `artefacts/tuple_in_characterisation.json` — the drift baseline for layer 3 (written by
  IX-05 on first run; later runs fail on drift, which is the intended behaviour).
* `artefacts/vector_insert_degradation.json` — **committed in an `unmeasured` state**. It
  carries the shape and the exact command that fills it, and says out loud that no cluster was
  reachable when it was authored. An artefact that does not say whether its numbers were
  measured is worse than no artefact, because it looks like evidence.
* `fixtures/plans/captured/` — plan text captured from a live cluster, so the difference
  between what the hand-written fixtures imagine CockroachDB prints and what it actually
  prints is visible rather than folklore.

## Ownership

The substrate under test is `packages/trappoint-recall/src/trappoint_recall/arms/`
(Apache-2.0, no database driver, no MAINLINE vocabulary). The MAINLINE bindings — table names,
index names, the facet vocabulary — live in `_support.py` in this directory, which is also what
proves the substrate is genuinely parameterised rather than parameterised-in-principle.

`prereq/00_consumed_tables.sql` is **read** from `tests/integration/recall_schema/`, not copied:
that file is owned by the DDL worker, and a second copy would drift from the real shapes.
