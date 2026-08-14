<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `qa/` — the numbers, and how to re-derive them

Everything in this directory is a **measurement**, not a target. Each file records what
some tool actually said about this repository at a stated moment, with the tool's version
next to it. If you think a number here is wrong, you can prove it in one command; the
command is printed inside the file it produces.

---

## `ruff-ratchet.json` — the lint and format ratchet

### What it is, in one paragraph

`ruff check .` currently reports **hundreds** of findings and `ruff format --check .`
reports **hundreds of files** that the formatter would rewrite. There were three things
we could do about that, and only one of them is honest.

| Option | What it costs | Why not |
|---|---|---|
| Run `ruff format .` and `ruff check --fix .` | rewrites ~240 files across ten workers' and eight leads' ownership | the diff becomes unreviewable and the wave becomes unmergeable; a reformat is also indistinguishable from a semantic edit in review |
| Delete the rules that fire | nothing, visibly | it is a lie. The preamble of `ruff.toml` explains why a blanket `except` and a naive `datetime` are product defects here, and deleting `BLE`/`DTZ` does not make them stop being that |
| **Count them, publish the count, refuse an increase** | one JSON file and one script | **this is what we did** |

So: `qa/ruff-ratchet.json` records the real number of findings **per rule per tree**, and
`scripts/qa/ruff_ratchet.py` refuses any commit that raises one of those numbers. A count
may fall freely. A count that rises names itself, its tree, its old value and its new
value, and exits non-zero.

**A truthful large number that cannot grow beats a fabricated zero.**

### Re-derive every number in the file, in one command

```
python scripts/qa/ruff_ratchet.py
```

Exit `0` means no rule/tree count increased. Exit `1` means one did, and it is named.
Exit `2` means the tooling itself is wrong (ruff missing, baseline missing, ruff version
does not match the one the baseline was taken with).

Nothing else is needed — no environment variables, no database, no network. The script
finds `.venv/Scripts/ruff.exe`, then `.venv/bin/ruff`, then `ruff` on `PATH`, and runs
exactly two commands, both of which are also written into the JSON under `commands`:

```
ruff check . --output-format json
ruff format --check --output-format json .
```

`--check` is not optional and is not a flag the script can be talked out of: the ratchet
**never rewrites a source file**. `tests/release/test_ruff_ratchet.py` enforces this by
reading the script's own source and asserting that none of the argv literals `"--fix"`,
`"--fix-only"`, `"--unsafe-fixes"` or `"format", "."` appear in it, and that
`"format", "--check"` appears exactly once.

### The five trees (plus a catch-all)

Every finding is bucketed by the first path segment that matches:

| tree | what lands there |
|---|---|
| `packages/trappoint-*` | the Apache substrate — the artefact a stranger forks |
| `packages/mainline-*` | first-party packages built on it |
| `verticals/` | the FSL vertical, including its own packages and tests |
| `tests/` | the root test tree |
| `scripts/` | operator tooling |
| `other/` | the deliberate catch-all: `skills/`, `infra/`, `spec/`, root-level modules. Nothing is silently dropped from the count. |

The split matters because the policy is a **gradient**, not a uniform standard. A missing
docstring on a test helper and a blanket `except` in the substrate are not the same
finding, and a single repo-wide total cannot say so.

### What is a hard gate

* A `(rule, tree)` pair recorded as **`0`** is a hard gate: the first finding fails.
* A `(rule, tree)` pair **absent** from `lint.rules` also defaults to `0`. A rule that
  has never fired in a tree is gated there the first time it does.

`policy.zero_tolerance` names the load-bearing families for `packages/trappoint-*` —
`BLE`, `E722`, `T20`, `S`, `DTZ`, `TRY300`, `RET` — the ones `ruff.toml`'s preamble says
are product defects rather than style nits. Every code in `at_zero_today` is written into
`lint.rules` as an explicit `0` so the gate stays visible even though ruff, quite
reasonably, reports nothing for a rule that does not fire.

### The part you should read before you trust the rest

`policy.zero_tolerance.declared_debt` says that **the substrate is not at zero**. Two of
the seven load-bearing families have live findings:

* `T201` (`print()`), 8 findings in `packages/trappoint-recall/.../lexical/digest.py`
* `S608` (hardcoded SQL expression), 4 findings in `packages/trappoint-recall/arms/`

They are **not waived**. `ruff.toml` does not relax them, no `# noqa` was added, and the
ratchet caps them at their true count so they cannot grow. They belong to files this
worker does not own, so they were recorded rather than fixed. The policy is zero
tolerance; the tree is not at zero; both sentences are in the JSON on purpose.

### Changing a number

| you want to | do |
|---|---|
| lower a count (you fixed something) | `python scripts/qa/ruff_ratchet.py --update` |
| raise a count (you are sure it is right) | `python scripts/qa/ruff_ratchet.py --rebaseline`, and say why in the PR |
| upgrade ruff | `--rebaseline`. The script refuses to compare across versions, because rule sets and default fixes differ between releases and a ratchet taken with a different ruff is not a ratchet. |

`--update` will **never** raise a count. If anything regressed it prints the refusal and
writes nothing, whatever flags you passed. Raising the number is allowed. Raising it
silently is not — that is the whole mechanism.

### The snapshot caveat, stated plainly

`generated_utc` is not decoration. This baseline was taken while ten workers were writing
to the same tree; the count moved from 793 to 820 in roughly twelve minutes of one
afternoon as a new distribution (`packages/trappoint-testkit/`) landed. **The first thing
to run on the merge commit is `--rebaseline`, once, deliberately, with the resulting
number quoted in the PR body.** After that the ratchet is a gate rather than a snapshot.
If `python scripts/qa/ruff_ratchet.py` exits 1 on a fresh clone with an unmodified tree,
that is what it is telling you.

### The formatter half

`format.unformatted_files` is the exact number of files `ruff format` would rewrite,
total and per tree. It is ratcheted the same way and **the formatter is never run without
`--check`**. The right time to spend that diff is a dedicated commit that touches nothing
else, on a quiet tree, with the number in this file going to `0` in the same commit.

---

## `cluster-known-red.json` — the cluster lane's inventory of failures it already knows about

### What it is, and the one property that matters

When `.github/workflows/cluster-tests.yml` points the demo-api suite at a real
CockroachDB, some tests fail for reasons that predate the lane. This file names every one
of them, with the cause and the lead who owns it. **It is an inventory, not a suppression
list**, and that is a structural property rather than a promise:

```
scripts/ci/cluster_lane_report.py --pytest-rc N   →   exits N when N is non-zero,
                                                      whatever this file says
```

Adding a node id here therefore **cannot** turn a red run green. It changes only the
sentence printed beside the failure — `known`, `unstable`, or **`NEW`**. The two verdicts
the report owns are both ones that fire when *pytest was green*:

| verdict | what it refuses |
|---|---|
| **the floor** (`floor.min_executed`, `floor.max_skipped`) | a lane that reached no database. `release-proof.yml:219-320` records the defect live in this repository: *pytest exits 0 when every test skips*, so a lane whose container failed to start runs 186 skips and reports success |
| **the ceiling** (`groups[].nodeids`) | an inventory larger than the truth. A node id listed here that **passes** is a hard failure, naming whoever fixed it and telling them to delete the line |

`unstable` is the one category the ceiling does not police, because the failing set for
this suite is measurably not deterministic. The schema refuses an `unstable` entry that
carries no `runs_observed`/`runs_failed`, and refuses one that failed **every** run it was
seen in — that is not unstable, it is failing, and it belongs in a group with a cause.

### The shape it is in today

| | |
|---|---|
| `groups` | **1** group, **1** node id — `mainline.defeater_option` holds zero rows, so a judge cannot choose a defeater and cannot sign |
| `unstable` | **4** node ids, all in `test_transitions.py`, all with measured counts |
| `floor.min_executed` | **518** — what CI run `31735341117` actually executed at `eefae1c` |
| `floor.max_skipped` | **1** — the one skip is `jsonschema is not a workspace dependency`, which has nothing to do with the database |

**`groups` is a ceiling that must reach empty.** One entry away.

### Re-derive the classification, in one command

```
python scripts/ci/cluster_lane_report.py \
  --junit <the run's junit.xml> \
  --known qa/cluster-known-red.json \
  --suite-root verticals/mainline/apps/demo-api/tests \
  --pytest-rc <pytest's REAL exit status>
```

`--pytest-rc` is not advisory and is not decoration. The report also refuses a run whose
JUnit records failures while the caller claims pytest exited 0 — the one rewiring that
would let a fully-inventoried red run present as green. `.github/workflows/cluster-lane-bites.yml`
proves both refusals every run, against a deliberately doctored copy of this file with
`min_executed: 0`, `max_skipped: 10000` and every failure declared known.

### The 2026-08-14 pruning, and why deleting 63 entries was not a ceiling falling for free

The file's own rule is *"entries leave it only in the commit that FIXES them"*. On
2026-08-14, 63 of the 64 inventoried ids passed — in CI and on this workstation — because
`eefae1c` landed the `demo_world.sql` build-out and the session-scoped `payloads` fixture
began to build. `docs/leads/lane-honest-plan.md` **R7** ruled that a landed, identifiable
fix discharges that rule **provided the deletion cites the commit by hash**: the rule
exists to stop a ceiling falling for an entry nobody fixed, not to freeze an inventory
because the fixing commit forgot to prune it. *A ceiling that cannot fall when the work is
provably done is a monument, not a ratchet.*

So the 62 fixed ids and the `reads-undeclared-query-parameter` group were deleted citing
`eefae1c`, and the attribution was **checked rather than assumed** — `git status` over the
seed and the reads paths printed nothing, so all of them are byte-identical to that commit
and the pass cannot be credited to a neighbour's uncommitted work. Both deleted groups'
`cause`, `cause_superseded` and `status_at_handoff` are preserved verbatim under the
top-level **`superseded`** key. The node ids themselves are recoverable in one command:

```
git show eefae1c:qa/cluster-known-red.json
```

A number replaced in place teaches nobody anything, which is the same convention
`ruff-ratchet.json` follows above.

### What may never be done to this file

* **Never** add a test that *started* failing — `policy.what_this_file_may_never_become`
  says so, and a new failure is reported **NEW**. The file records, by name and with the
  reason, every occasion somebody declined to: three 40001 `RETRY_SERIALIZABLE` setup
  errors on 2026-08-14, and 29 failures downstream of another lead's uncommitted work
  later the same day.
* **Never** lower `min_executed`, raise `max_skipped`, or delete a group to obtain a green.
  `min_executed` may rise and `max_skipped` may fall as the suite is repaired; moving
  either the other way is the single most damaging edit available here.
* **Never** fold observations from a different source tree into an `unstable` entry's
  counts. `how_the_unstable_counts_were_folded` records a case where doing so would have
  turned a *deterministic* breakage of an uncommitted tree into *flakiness* of a committed
  one — which is precisely the loophole `unstable` is fenced against. The rejected numbers
  are recorded beside the accepted ones so the choice is auditable.
* `measured_executed` and `measured_skipped` are **historical**: they record the run that
  set the floor, not a live reading. Live readings are appended, dated, and carry the
  command that produced them, under `measured.re_measured`.

---

## Sibling artefacts

`qa/mypy-ratchet.json` and `scripts/qa/mypy_targets.py` (type coverage) are owned by a
different worker in this wave and follow the same convention this file describes:
**measure, publish the measurement with the tool version beside it, and let a reader
re-derive it in one command.** `scripts/qa/doctor.py` (environment preflight) is expected
to join them. Read each artefact's own header for its command; do not assume this one's.
