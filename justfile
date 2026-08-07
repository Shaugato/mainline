# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# The command surface a stranger uses. Every recipe here is something PL-1 says must
# work on a machine that has never held one of our credentials:
#
#     just up && just bootstrap && just conform
#
# is the entire K1 proof. If a recipe needs an AWS account or a CockroachDB Cloud
# organisation, it does not belong in this file.
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

set shell := ["bash", "-euo", "pipefail", "-c"]
set windows-shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := false

# The local single-node DSN. `--insecure` means no password: this cluster is bound to
# loopback in compose.yaml and is not a place to put anything real.
LOCAL_DSN := "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"

# The reference vertical's rendered SQL. `--profile trappoint-ref` is what makes K1
# independent of K3 — see docs/leads/kernel.md §1.1.
REF_MIGRATIONS := "packages/trappoint-sql/refvertical/sql"
MAINLINE_MIGRATIONS := "verticals/mainline/db/migrations"

_default:
    @just --list --unsorted

# ── The cluster ──────────────────────────────────────────────────────────────

# Start the local single-node CockroachDB and wait for it to answer SQL.
up:
    docker compose -f compose.yaml up -d --wait
    @echo "cluster up · $(just image) · DSN: {{LOCAL_DSN}}"

# Stop the cluster, keeping the data volume.
down:
    docker compose -f compose.yaml down

# Stop the cluster AND destroy its data. The honest reset before a clean proof run.
nuke:
    docker compose -f compose.yaml down --volumes --remove-orphans

# Print the pinned CockroachDB image. One constant, read out of compose.yaml.
image:
    @uv run --package trappoint-migrate trappoint migrate image

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

# The K1 proof. Exits non-zero until the DDL that owns each case has landed.
conform:
    uv run --package trappoint-conformance trappoint-conform --dsn '{{LOCAL_DSN}}' --profile trappoint-ref

# The same suite against MAINLINE. Blocked on K3; see docs/leads/kernel.md §5 risk 1.
conform-mainline:
    uv run --package trappoint-conformance trappoint-conform --dsn '{{LOCAL_DSN}}' --profile mainline

# List every case the manifest declares for a profile, and which are implemented.
cases:
    uv run --package trappoint-conformance trappoint-conform --profile trappoint-ref --list

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

# Hermetic tests only: nothing here needs a cluster, a credential or a network.
test:
    uv run --package trappoint-migrate pytest packages/trappoint-migrate/tests -q

# Re-resolve uv.lock after a package adds a dependency. Never hand-edit the lockfile.
lock:
    uv lock

# Assert the lockfile is exactly what the pyproject files imply.
lock-check:
    uv lock --check
