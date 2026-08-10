<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# trappoint-testkit

**One cluster, not thirteen.** A pytest plugin and a small library that give the whole test
session a single CockroachDB, hand each test module its own database inside it, and make the
no-cluster case a skip with a reason instead of a wedged machine.

Everything below was measured on 2026-08-10 against CockroachDB CCL v26.2.5 on this
repository's local node. Nothing in it is inferred.

---

## The two defects this package exists to remove

### 1. Thirteen concurrent single-node clusters

A full-suite run produced this from `docker ps -a`:

```
mainline-cbm-test              Exited (7)   mainline-recall-index-test     Exited (7)
mainline-deltalattice-test     Exited (7)   mainline-recall-lexical-test   Exited (8)
mainline-directrix-test        Exited (7)   mainline-blame-schema-test     Exited (7)
mainline-origindiff-test       Exited (7)   mainline-event-severity-…      Exited (8)
mainline-late-recall-test      Exited (8)   mainline-cbm-probe             Created
mainline-custody-nemesis       Exited (7)   trappoint-model-differential   Exited (7)
trappoint-model-concurrency    Exited (8)
```

Thirteen nodes, each started with `--cache=.25 --max-sql-memory=.25`, is thirteen quarters of
the machine's memory. They died, they took the real node `mainline-crdb` down with them, and
the Docker engine API began answering `500 Internal Server Error`.

### 2. The suite hung rather than failed

Fixtures connect without `connect_timeout`. Measured here, connecting to a black-holed
address:

| | time to raise |
|---|---|
| no `PGCONNECT_TIMEOUT` | **130.1 s** |
| `PGCONNECT_TIMEOUT=3` | **3.1 s** |

`pytest-timeout`'s thread method cannot interrupt a hang inside *session-scoped fixture
setup*, so `timeout = 120` in `pyproject.toml` never fired. A suite that hangs has stopped
asserting anything, and it does not even have the decency to be red.

---

## The seam — why no domain fixture had to be edited

Twenty-three source files spawn containers. **Every one of them checks an environment DSN
first** and only reaches for Docker when it is unset. Four spellings are in use, counted
across `*.py`:

| variable | occurrences |
|---|---|
| `MAINLINE_TEST_DSN` | 28 |
| `COCKROACH_URL` | 19 |
| `CRDB_URL` | 17 |
| `TRAPPOINT_DSN` | 3 |

Publish one DSN under all four and thirteen clusters collapse into one with **zero edits to
those twenty-three files**.

The same seam exists for the image. `compose.yaml` declares itself the single source of the
version constant — *"THE VERSION CONSTANT LIVES HERE AND ONLY HERE"* — but measured across
`*.py` there were **33 uses of the floating tag `cockroachdb/cockroach:latest-v26.2` against
10 of the pinned `v26.2.5`**. Every one of the 33 spells it
`os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:latest-v26.2")`, so exporting
the variable means the floating default is never reached. `image.py` parses the pin out of the
line tagged `# trappoint:crdb-image-pin` and exports it under `CRDB_IMAGE`,
`MAINLINE_CRDB_IMAGE` and `TRAPPOINT_CRDB_IMAGE`.

---

## Usage

```
pytest --crdb=auto     # reuse a node that answers; start exactly one if none does (default)
pytest --crdb=reuse    # reuse or nothing — never starts a container (what CI wants)
pytest --crdb=spawn    # always this package's own container, replacing a stale one
pytest --crdb=none     # do not look, and stop anything else looking: cluster tests SKIP
```

`TRAPPOINT_CRDB_MODE` sets the default when the flag is absent. `TRAPPOINT_TESTKIT_TEARDOWN=1`
removes the container at session end; by default it is left running so the next run's `auto`
is a reuse.

The header says what happened, every run:

```
trappoint-testkit: --crdb=auto, image=cockroachdb/cockroach:v26.2.5
trappoint-testkit: reused, the compose port — CockroachDB CCL v26.2.5
trappoint-testkit: postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable
trappoint-testkit: gc.ttlseconds left alone cluster-wide (node not started by this package)
```

### Fixtures

| fixture | scope | what it is |
|---|---|---|
| `shared_cluster` | session | the one `SharedCluster`, or a skip naming what is missing |
| `crdb_database` | **module** | a database of this module's own, dropped afterwards |
| `crdb_dsn` | module | that database's DSN |
| `crdb_conn` | function | one autocommit connection into it |

Isolation is per **module**, not per session and not per test. Per session lets one module's
leftovers explain another module's pass; per test would re-apply a migration band for every
assertion and be honest but unusable.

---

## `gc.ttlseconds` is pinned to Cloud's value, not left at local's

Local defaults to **14400**. CockroachDB Cloud Basic is **4500**. Local is therefore *more
permissive than production*, and a time-travel test that passes on a laptop at 14400 is not
evidence that it passes on Cloud. Every database this package creates is pinned to 4500, and
a node this package *started* has its default range pinned too.

A node it merely **borrowed** is never reconfigured cluster-wide. It belongs to whoever
started it, and per-database pinning already covers what our tests touch.

---

## `--crdb=none` and the `ProcessGuard`

Unsetting the DSN is not enough. With no DSN, each of the twenty-three fixtures walks its own
discovery ladder — `shutil.which("cockroach")`, then `docker info` (which **blocks** for the
full ten-second probe against a dead daemon), then `docker run`. That ladder is what produced
thirteen containers.

So `--crdb=none` cuts the ladder at its first rung. `ProcessGuard` makes `shutil.which` report
`docker`, `podman`, `nerdctl` and `cockroach` as absent, and makes `subprocess.run` / `Popen`
refuse to launch them with `FileNotFoundError`. Every one of those fixtures already catches
`OSError` to mean "no Docker here" — so each reaches **its own** `pytest.skip`, with **its
own** reason, which is a better message than this package could write on their behalf.

It is narrow on purpose: only those executables are blocked, so a test that shells out to
`git` or `python` is untouched. Patching the module attribute is sound here because no file
in `tests`, `packages`, `verticals` or `scripts` writes `from subprocess import run` —
verified by grep, not assumed.

---

## What this package does not claim

* It does not make the suite hermetic. `packages/` still contains tests that need a database;
  they now share the session's one node instead of each building their own.
* It does not verify any schema. It obtains a cluster and gets out of the way.
* `--crdb=none` producing a green run proves only that the non-cluster tests pass. **A skipped
  cluster test is not evidence**, and every skip says so in its own words.
