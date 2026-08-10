# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# The command surface a stranger uses. Every recipe here is something PL-1 says must
# work on a machine that has never held one of our credentials:
#
#     just up && just bootstrap && just conform
#
# is the entire K1 proof, and
#
#     just up && just doctor && just prove
#
# is the whole product claim: a real refusal, out of a real database, on a laptop.
# If a recipe needs an AWS account or a CockroachDB Cloud organisation, it does not
# belong in this file.
#
# Bash on every platform, including Windows, where Git Bash ships with Git. `just`'s
# default Windows shell is cmd.exe, and a repository whose proof command differs by
# operating system has two proofs.
#
# Every `uv run` is SCOPED — `--package`, `--only-group dev`, or `--all-packages` where
# the check genuinely needs the whole graph. A bare `uv run` builds every workspace
# member, which would make `just image` fail because some unrelated distribution three
# directories away is mid-edit. In a repository built by many hands at once that is not
# a hypothetical; it is Tuesday.
#
# FOUR RECIPES MAY NOT MENTION `uv`, AND THAT IS LOAD-BEARING. Measured on 2026-08-10:
# `uv` was not installed on the machine this repository is built on, and every recipe in
# this file began with `uv run`. A stranger's first command therefore answered
# `uv: command not found` from a file whose own header promised it ran on a stranger's
# laptop. `doctor`, `setup`, `up` and `pin` run BEFORE uv exists, so none of them may
# reach it — not directly, and not one hop away either, which is how `up` used to break:
# it called `just image`, and `image` is `uv run`. `doctor` says what is missing, `setup`
# installs it. Everything after them may — and does — assume the workspace.
# `tests/release/test_one_command_loop.py` walks the reachable set and enforces this.

set shell := ["bash", "-euo", "pipefail", "-c"]
set windows-shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := false

# The interpreter that runs `doctor`, and $PYTHON always wins.
#
# The probe RUNS the candidate rather than looking it up, and that is not pedantry.
# Measured here: `command -v python3` succeeds on this Windows machine and points at
# `…/WindowsApps/python3`, the Microsoft Store execution alias, which exits 49 with
# "Python was not found; run without arguments to install from the Microsoft Store".
# A PATH lookup would have chosen it. `python3 -c "import sys"` does not.
PYTHON := env_var_or_default("PYTHON", `python3 -c "import sys" >/dev/null 2>&1 && echo python3 || echo python`)

# The local single-node DSN. `--insecure` means no password: this cluster is bound to
# loopback in compose.yaml and is not a place to put anything real.
LOCAL_DSN := "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"

# The reference vertical's rendered SQL. `--profile trappoint-ref` is what makes K1
# independent of K3 — see docs/leads/kernel.md §1.1.
REF_MIGRATIONS := "packages/trappoint-sql/refvertical/sql"
MAINLINE_MIGRATIONS := "verticals/mainline/db/migrations"

_default:
    @just --list --unsorted

# ── The four commands ────────────────────────────────────────────────────────
#
# docs/release/QUICKSTART.md is these and nothing else.

# Preflight. Says what is missing, and the command that fixes it, before anything fails.
doctor:
    @{{PYTHON}} scripts/qa/doctor.py

# Install uv if it is absent, then resolve and install every workspace member.
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v uv >/dev/null 2>&1 ; then
        echo "uv already present: $(uv --version)"
    else
        echo "uv is not installed. Installing it — this is the one bootstrap step."
        if [ "${OS:-}" = "Windows_NT" ] ; then
            powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
            export PATH="$HOME/.local/bin:$PATH"
        else
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.local/bin:$PATH"
        fi
        command -v uv >/dev/null 2>&1 || {
            echo ""
            echo "uv installed but is not on PATH in this shell. Open a new terminal, or:"
            echo '    export PATH="$HOME/.local/bin:$PATH"'
            exit 1
        }
    fi
    uv sync --all-packages
    echo ""
    echo "workspace installed. Next:  just up && just doctor && just prove"

# Bootstraps, applies the whole migration chain into a throwaway database, attempts the
# merge three times, and prints the refusal the database actually issued — SQLSTATE,
# constraint name and all. Exit 0 means proven; exit 1 means NOT proven and the evidence
# file says which half failed. Publish either one.
#
# THE recipe: a real refusal, out of a real database, on a laptop, in one command.
prove:
    uv run --package trappoint-migrate python scripts/proof/gate_refusal.py --dsn '{{LOCAL_DSN}}'

# ── The cluster ──────────────────────────────────────────────────────────────

# Start the local single-node CockroachDB, wait for it to answer SQL, align it with Cloud.
up:
    docker compose -f compose.yaml up -d --wait
    @just gc-align
    @echo "cluster up · $({{PYTHON}} scripts/qa/doctor.py --print-pin) · DSN: {{LOCAL_DSN}}"

# Local defaults to gc.ttlseconds 14400 — four hours of MVCC history against Cloud
# Basic's seventy-five minutes — so local is the MORE permissive of the two, and a
# time-travel assumption that is legal here is refused on the nightly Cloud run.
# Idempotent; `just up` runs it for you.
#
# Pin local `gc.ttlseconds` to 4500, the value CockroachDB Cloud Basic enforces.
gc-align:
    @docker compose -f compose.yaml run --rm crdb-align

# Stop the cluster, keeping the data volume.
down:
    docker compose -f compose.yaml down

# Stop the cluster AND destroy its data. The honest reset before a clean proof run.
nuke:
    docker compose -f compose.yaml down --volumes --remove-orphans

# Print the pinned CockroachDB image. One constant, read out of compose.yaml.
image:
    @uv run --package trappoint-migrate trappoint migrate image

# The same constant, read without uv — because `up` runs before `setup` has installed it.
pin:
    @{{PYTHON}} scripts/qa/doctor.py --print-pin

# Print the local DSN, for `export LOCAL_DSN="$(just dsn)"`.
dsn:
    @echo '{{LOCAL_DSN}}'

# Open a SQL shell on the local cluster.
sql:
    docker exec -it trappoint-crdb ./cockroach sql --insecure

# ── The schema ───────────────────────────────────────────────────────────────

# The `trappoint` bookkeeping schema (D6): migration, lock, attestation.
bootstrap:
    uv run --package trappoint-migrate trappoint migrate bootstrap --dsn '{{LOCAL_DSN}}'

# Apply the reference vertical's migrations, forward only, one statement per file.
migrate:
    uv run --package trappoint-migrate trappoint migrate up --dsn '{{LOCAL_DSN}}' --tree trappoint-ref --migrations '{{REF_MIGRATIONS}}'

# Apply the MAINLINE vertical's migrations.
migrate-mainline:
    uv run --package trappoint-migrate trappoint migrate up --dsn '{{LOCAL_DSN}}' --tree mainline --migrations '{{MAINLINE_MIGRATIONS}}'

# What is applied, what is pending, what is dirty, and the attestation chain head.
status:
    uv run --package trappoint-migrate trappoint migrate status --dsn '{{LOCAL_DSN}}' --tree trappoint-ref --migrations '{{REF_MIGRATIONS}}'

# Recompute the schema fingerprint and compare it with the attestation head.
# Non-zero exit means the live schema drifted from what the ledger says was applied.
attest:
    uv run --package trappoint-migrate trappoint migrate attest --dsn '{{LOCAL_DSN}}'

# ── The refusal ──────────────────────────────────────────────────────────────

# Resolve the conformance runner without assuming uv. MEASURED 2026-08-10: uv is not on
# PATH on the machine this repository is built on, and `conform`, `conform-mainline` and
# `cases` all began with `uv run` — so `just up && just bootstrap && just conform`, the
# sequence this file's own header calls the entire K1 proof, answered
# `uv: command not found`. The repository venv is tried first because it is what a
# checkout that ran `just setup` (or a plain `pip install -e`) actually has; uv remains a
# fallback, scoped, for a workspace that prefers it. Underscore-prefixed: `just --list`
# shows the three recipes a reader wants, not the plumbing under them.
_conform *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    if   [ -x .venv/Scripts/trappoint-conform.exe ] ; then RUNNER=(.venv/Scripts/trappoint-conform.exe)
    elif [ -x .venv/bin/trappoint-conform ]         ; then RUNNER=(.venv/bin/trappoint-conform)
    elif [ -x .venv/Scripts/python.exe ]            ; then RUNNER=(.venv/Scripts/python.exe -m trappoint_conformance.cli)
    elif [ -x .venv/bin/python ]                    ; then RUNNER=(.venv/bin/python -m trappoint_conformance.cli)
    elif command -v uv >/dev/null 2>&1              ; then RUNNER=(uv run --package trappoint-conformance trappoint-conform)
    elif command -v trappoint-conform >/dev/null 2>&1 ; then RUNNER=(trappoint-conform)
    else
        echo "no conformance runner found." >&2
        echo "  the repository venv:  python -m venv .venv && .venv/bin/pip install -e packages/trappoint-conformance" >&2
        echo "  or the workspace:     just setup" >&2
        exit 1
    fi
    echo "── ${RUNNER[*]} {{ARGS}}"
    "${RUNNER[@]}" {{ARGS}}

# The K1 proof. Exits non-zero until the DDL that owns each case has landed.
conform:
    @just _conform --dsn '{{LOCAL_DSN}}' --profile trappoint-ref

# The same suite against MAINLINE, resolving every `requires` against the live cluster.
conform-mainline:
    @just _conform --dsn '{{LOCAL_DSN}}' --profile mainline --autodetect-requires

# List every case the manifest declares for a profile, and which are implemented.
cases:
    @just _conform --profile trappoint-ref --list

# Writes qa/conformance-census.json and docs/release/conformance-census.md. Extra
# arguments pass straight through, so `just conform-census --run-id w9-20260810` pins
# the tenancy and a second run at the same id lands on the same rows.
#
# Build a migrated MAINLINE database, run all 71 cases, publish pass/fail/cannot-run per case.
conform-census *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    if   [ -x .venv/Scripts/python.exe ] ; then PY=(.venv/Scripts/python.exe)
    elif [ -x .venv/bin/python ]         ; then PY=(.venv/bin/python)
    elif command -v uv >/dev/null 2>&1   ; then PY=(uv run --package trappoint-conformance python)
    else PY=({{PYTHON}})
    fi
    echo "── ${PY[*]} scripts/qa/run_conformance_census.py --build {{ARGS}}"
    "${PY[@]}" scripts/qa/run_conformance_census.py --build {{ARGS}}

# PL-2, on demand: the whole red-before-green sequence from an empty machine.
red: up bootstrap
    @echo "── observing the conformance suite RED (this SHOULD fail) ──"
    @if just conform ; then echo "GREEN — update docs/adr/0005-red-before-green.md" ; else echo "RED, as PL-2 requires" ; fi

# ── The guards ───────────────────────────────────────────────────────────────

# Every static check CI runs, in the order that fails fastest.
lint: lint-sql lint-py lint-types lint-imports

# The sequence ban (D10) and the invariant-citation rule, over every migration tree.
lint-sql:
    uv run --package trappoint-migrate trappoint migrate lint --root '{{REF_MIGRATIONS}}' --root '{{MAINLINE_MIGRATIONS}}' --root packages/trappoint-sql/templates

# ruff, over the whole repository.
lint-py:
    uv run --only-group dev ruff check .
    uv run --only-group dev ruff format --check .

# mypy, strict on the Apache substrate (see mypy.ini for the gradient).
lint-types:
    uv run --only-group dev mypy --config-file mypy.ini packages/trappoint-migrate/src/trappoint_migrate packages/trappoint-conformance/src/trappoint_conformance

# The four contracts. Needs every workspace member installed: `uv sync --all-packages`.
lint-imports:
    uv run --all-packages lint-imports --config .importlinter

# Apply the formatter and every safe autofix.
fmt:
    uv run --only-group dev ruff format .
    uv run --only-group dev ruff check --fix .

# ── The tests ────────────────────────────────────────────────────────────────
#
# `--crdb` is trappoint-testkit's, and it is the difference between a suite and a
# machine on fire. Measured on 2026-08-10: an unqualified full-suite run started
# THIRTEEN private single-node CockroachDB containers concurrently, all thirteen exited
# 7 or 8, they took the real node down with them, and the Docker engine API began
# answering HTTP 500. `--crdb=none` starts none and skips every cluster test with the
# reason its own fixture writes; `--crdb=reuse` uses the ONE container `just up` started
# and will never start a second.

# The hermetic suite: no cluster, no credential, no network. This is what CI runs first.
test:
    uv run --all-packages pytest --crdb=none

# The same suite with the cluster tests live, against the one container `up` started.
test-cluster: up
    uv run --all-packages pytest --crdb=reuse

# The console's own gate: eslint, tsc twice, vitest, vite build, budgets, licences.
console:
    cd verticals/mainline/apps/console && pnpm install --frozen-lockfile && pnpm run ci

# Re-resolve uv.lock after a package adds a dependency. Never hand-edit the lockfile.
lock:
    uv lock

# Assert the lockfile is exactly what the pyproject files imply.
lock-check:
    uv lock --check
