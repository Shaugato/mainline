<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `cluster-lane-bites` 2×2 — the raw artefacts

Produced by W4 of the lane-controls wave on **2026-08-14**, on TRAPPOINT, against local
**CockroachDB CCL v26.2.5** at `127.0.0.1:26257`, working tree at HEAD `538193b`.

The analysis is [`docs/ci/cluster-lane-falsifiability.md`](../../../docs/ci/cluster-lane-falsifiability.md).
**Every number in that document is read out of these files**, not off a terminal scroll —
this suite is I/O-bound and silent for minutes, and healthy runs have been killed for looking
hung.

## How they were produced

```
SUB="verticals/mainline/apps/demo-api/tests/test_credentials.py
     verticals/mainline/apps/demo-api/tests/test_gate_run.py
     verticals/mainline/apps/demo-api/tests/test_transitions.py"

.venv/Scripts/python.exe -m pytest $SUB --crdb=<none|reuse> -q -p no:cacheprovider \
    --junitxml=evidence/ci/cluster-lane-2x2/<file>.xml
```

The plant was applied and removed with `scripts/ci/plant_cluster_defect.py`
(`--plant seed-credential-swap` / `--revert`) between the plant-absent and plant-present
cells, twice. `demo_world.sql` hashes `e2aa9706ffca80f2…` before and after both cycles.

## The files

| file | cell | plant | `--crdb` | collected/executed/skipped/fail/err/passed |
|---|---|---|---|---|
| `junit-absent-cluster.xml` | 1, attempt 1 | absent | `reuse` | 78 / 77 / 1 / 0 / 1 / 76 |
| `junit-absent-cluster-attempt2.xml` | 1, attempt 2 | absent | `reuse` | 78 / 77 / 1 / 0 / 0 / 77 |
| `junit-absent-cluster-attempt3.xml` | 1, attempt 3 | absent | `reuse` | 78 / 77 / 1 / 0 / 0 / 77 |
| `junit-absent-cluster-attempt4.xml` | 1, attempt 4 | absent | `reuse` | 78 / 77 / 1 / 0 / 0 / 77 |
| `junit-absent-hermetic.xml` | 2 | absent | `none` | 78 / 7 / 71 / 0 / 0 / 7 |
| `junit-planted-hermetic.xml` | 3 | **present** | `none` | 78 / 7 / 71 / 0 / 0 / 7 |
| `junit-planted-cluster.xml` | 4, attempt 1 | **present** | `reuse` | 78 / 67 / 11 / 2 / 2 / 63 |
| `junit-planted-cluster-attempt2.xml` | 4, attempt 2 | **present** | `reuse` | 78 / 70 / 8 / 1 / 0 / 69 |

`summary.json` — the same numbers plus the failing, erroring and executed node-id lists,
generated from the XML rather than typed in. Its `cell2_vs_cell3` block is the assertion the
whole wave turns on: `counts_equal: true`, `executed_nodeid_sets_identical: true`.

`fresh-migration-build-control.json` — a control run for finding 2 of the analysis: the same
271 migrations applied into throwaway databases on a **clean** tree with no plant present,
**271 applied / 0 failed, twice**. It establishes that the partial build failures seen inside
the plant-present cluster cell are not caused by the plant and not caused by the migration
set.

## Why there are more than four files

Cell 1 was **red on its first attempt** (an unretried `40001 RETRY_SERIALIZABLE` in
`test_transitions.py::_seed_permit`) and green on the three that followed. Cell 4 was red
twice for different reasons, and only the second attempt is a falsifiability proof — on the
first, the test the plant's manifest names was *skipped* rather than failed, because the
database it needed did not finish building.

**The first attempt of each is kept and is the one the analysis treats as canonical.** The
extra runs are the flake measurement, not a search for a greener number. Nothing here was
re-run until it passed, and no floor, fixture or expected value was moved to obtain any
result in this directory.

## What these artefacts do NOT show

The workflow's `git diff --exit-code` and empty-`git status --porcelain` assertions were
**not** exercised. This working tree carried 52 modified and 42 untracked files when the
measurement opened and 51/42 when it closed — other workers are editing it concurrently — so
both assertions would fail here for reasons unrelated to the plant. They are CI-only and will
be validated on a clean checkout. Nothing in this directory should be read as evidence that
they pass.
