<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0005 — The kernel's conformance lane is committed RED, and the red run is the artefact

**Status:** Accepted · **Date:** 2026-08-07 · **Decider:** kernel lead · **Milestone:** K1
**Implements:** `docs/leads/kernel.md` §1.3 · **Discipline:** PL-2 (red before green)

## Context

TRAPPOINT's deliverable is a **refusal**. `CF-01` says: merge a permit carrying one open
blocking check, and the database must answer `23514` on `gate_closed_when_issued`.

For a product of that shape a green suite proves almost nothing on its own, because a
suite that has never been red is equally consistent with two states of the world:

- the gate refuses the write, or
- the case never reached the gate, and the assertion is decoration.

The second state is not hypothetical. It is the ordinary outcome of writing a test
against code that already exists, and it is the first thing an opposing expert looks
for. *"Your conformance suite passes 45/45"* is worth nothing if the answer to *"did any
of those cases ever fail?"* is *"we never checked."*

BUILD_PLAN.md §0.2 states the rule that follows:

> **PL-2 — Red before green.** A milestone begins with the failing test its exit
> criterion asserts, not with implementation. `db.yml` runs a CockroachDB service
> container and **one failing conformance case before any schema exists**. For a product
> whose deliverable is a refusal, a suite that has never been red asserts nothing — and a
> solo founder building with coding agents accumulates confidently-written tests that
> assert nothing faster than anyone else.

## Decision

**The conformance lane is committed in a state where it fails, and it is not marked
`continue-on-error`.**

Concretely:

1. `packages/trappoint-conformance` ships **exactly one** case, `CF-01`, inline in
   `runner.py`. The remaining seventy cases in `spec/conformance/manifest.toml` are
   reported as `PENDING` — printed and counted, never silently absent.
2. `.github/workflows/db.yml` starts a single-node CockroachDB, runs
   `trappoint migrate bootstrap`, `up`, `attest`, and then `trappoint-conform`. The last
   step fails. The job is red.
3. Every later kernel worker turns **only** the cases its brief names, from red to green,
   and may not touch a case it does not own.
4. The conformance-corpus worker owns `test_manifest_totality`, which is bidirectional:
   a manifest entry with no implementation, or an implementation with no manifest entry,
   fails CI. That is what converts today's benign `PENDING` count into a hard gate.

### A red case and a broken runner must not look alike

This is the part that makes the discipline survivable rather than merely virtuous. If
the ordinary pre-migration state produced a stack trace, nobody could tell PL-2 red from
a genuinely broken lane, and within a week the lane would be ignored.

So the runner classifies. `42P01`, `42883`, `3F000` and their neighbours are recorded in
`sqlstate.py` as **schema-absent** codes. They are still failures — the taxonomy is total
over `{40001, 23514, 23503, 23505, P0001}` and everything else fails the suite — but they
fail with a sentence that names the missing object:

```
SCHEMA NOT MIGRATED — CF-01: expected 23514 on 'gate_closed_when_issued';
observed 42P01 is outside the modelled taxonomy — the schema is not migrated to the
version this case expects. … Message: relation "trappoint_ref.permit" does not exist
```

And *"there was no database"* exits through its own path with its own sentence, because
it is a different claim from *"the database said no."*

## The observed red run

### Locally, on a real cluster — 2026-08-07

Docker was unavailable on the build machine, so the cluster was the released CockroachDB
binary run directly. This is stronger evidence than a mock, and weaker than CI, and both
halves of that sentence matter.

| | |
|---|---|
| Cluster | CockroachDB **CCL v26.2.5**, `x86_64-w64-mingw32`, built 2026-07-28, `go1.25.5` |
| Mode | `start-single-node --insecure`, loopback only |
| Command | `trappoint-conform --dsn "$LOCAL_DSN" --profile trappoint-ref` |
| Exit code | **1** |

```
FAIL  CF-01  Merge a permit carrying one open blocking check
        SCHEMA NOT MIGRATED — CF-01: expected 23514 on 'gate_closed_when_issued';
        observed 42P01 … Message: relation "trappoint_ref.permit" does not exist
PEND  44 case(s) declared in the manifest have no implementation yet …

0/45 · spec 1.0.0-rc.1 · profile trappoint-ref · failed 1 · pending 44
```

Exactly one failing case. The failure names a **missing relation**, not a harness error.
That is the PL-2 artefact.

The whole of `db.yml` was then replayed through `uv run --frozen --package …` — the
exact invocations the workflow uses — against the same cluster: `lint`, `bootstrap`,
`up`, `attest`, `conform --list`, `conform`. Same result, same exit codes.

The rest of the K1 toolchain was exercised against the same cluster in the same session
and behaved as designed: `bootstrap` (idempotent, genesis attestation written), `up`
(no-op on an empty tree; four migrations applied on a smoke tree), the dirty marker
(a failing statement recorded `42P01` and forward progress was refused until
`force --incident` cleared it), checksum-change / out-of-order-insertion /
deleted-applied-file detection, lease contention and expired-lease takeover, and chain
tampering (a deleted attestation row was reported as a gap; a rewritten one as a
rewrite).

### In GitHub Actions

```
run_url: UNRECORDED
```

The repository has no pushed CI history as of 2026-08-07, so there is no run URL to
record and inventing one would defeat the purpose of the field. This is enforced rather
than left to memory: the `adr-red-recorded` job in `.github/workflows/ci.yml` **warns**
on a pull request and **fails on a push to `main`** while `run_url` still reads
`UNRECORDED`. The first push to `main` after the `db` lane runs is therefore the commit
that has to fill it in.

## Consequences

**The `db` lane is red on `main`, on purpose, until the kernel DDL lands.** Anyone
reading the badge should read this ADR. The alternative — keeping the lane green by not
having a case in it — is the state PL-2 exists to prevent.

**`continue-on-error` is never added to the conform step.** A red lane that reports green
is worse than no lane at all.

**A case may only be made green by the migration that owns it.** Softening an assertion,
widening an expected SQLSTATE, or relaxing an exhibit name to make a lane pass is a
change to the specification, and `spec/conformance/manifest.toml` is where that argument
has to be had.

**`PENDING` is temporary and visible.** It is printed on every run and it does not make
the run green. Once `test_manifest_totality` lands, it is fatal.

## Platform findings recorded in passing

Two things were measured while collecting the evidence above, and both are worth having
written down because they were open questions:

- **CockroachDB v26.2.5 exists as a released, downloadable binary** (including for
  Windows), which is what `compose.yaml` pins.
- **GT-05 is answered `PASS` on v26.2.5 for the local single-node case.** Both
  `pg_get_triggerdef` and `pg_get_functiondef` are present in `pg_catalog.pg_proc`, so
  `trappoint migrate attest` reports `grade strong` and the self-attesting-gate claim
  holds. This is **not** yet verified on CockroachDB Cloud Standard, where the SQL
  identity differs; the runner probes rather than assumes, and writes
  `attestation_grade = 'weak'` into the row wherever the fallback is taken.

- **`cockroach start-single-node --background` was removed.** The flag errors with
  `unknown flag: --background` on v26.2.5. Anything that shells out to start a local node
  must supervise the process itself.

- **Every `uv run` in this repository must be scoped.** A bare `uv run` builds *every*
  workspace member, so a command with no relationship to a package fails while that
  package is mid-edit — which, in a repository written by many hands at once, is the
  normal state rather than the exception. The `justfile` and both workflows therefore use
  `uv run --package <name>`, `--only-group dev`, or `--all-packages` where the check
  genuinely needs the whole graph (import-linter does).

## Alternatives considered

**Write the DDL first and the suite after.** Rejected: it produces a suite that describes
what was built rather than one that constrains it, and it forfeits the only cheap
evidence that the cases assert anything.

**Keep the lane green by making CF-01 skip until the schema exists.** Rejected, and it is
the tempting one. A skip is invisible in a badge, and "skips while the schema is absent"
is one refactor away from "skips because a fixture went missing." A skipped case is never
a passed case, and the runner is built so that the two can never be confused.

**Assert only the SQLSTATE, not the constraint name.** Rejected by `spec/errors.md` §3.1:
*"an exception was raised"* is worthless in a product whose deliverable is the diagnosis.
`CF-01` asserts `23514` **and** `gate_closed_when_issued`, and the right code from the
wrong mechanism fails.
