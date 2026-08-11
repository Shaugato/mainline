<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The two mechanical sweeps

**Worker:** W10, the completion wave's exclusive tree lock. **Measured:** 2026-08-11,
against `github.com/Shaugato/mainline`, branch `master`, starting from commit `8e8c0b3`.

Two repository-wide rewrites were scheduled last in the wave, alone, so that neither
would make another worker's diff unreadable. **One landed. One did not, and the reason it
did not is the most useful thing in this document.**

---

## 0. The measurement trap both sweeps sit in

`git config core.autocrlf` is **`true`** in this checkout and there is no `.gitattributes`.
`ruff.toml` pins `line-ending = "lf"`. So every file git had checked out through the CRLF
filter counted as unformatted on Windows and did not count as unformatted on the runner:

```
$ .venv/Scripts/python.exe -m ruff format --check .          # Windows working tree
261 files would be reformatted, 1166 files already formatted

$ git -c core.autocrlf=false worktree add --detach <tmp> HEAD
$ <tmp>/.venv/Scripts/ruff.exe format --check .              # what CI sees
207 files would be reformatted, 1190 files already formatted
```

153 of 1 190 `.py` files carried CRLF in the working tree and LF in the object database.
**The brief's 247 and the lead plan's 249 are both artefacts of that filter.** Every number
below was taken on a fresh LF worktree, which is the only tree CI can reproduce.

> If you are re-taking any count in this repository on Windows, take it in a worktree
> created with `git -c core.autocrlf=false -c core.eol=lf worktree add --detach`, and say
> so next to the number.

---

## 1. Sweep one — `ruff format .` — **LANDED**

`f229c1b` (two instruments), `998c526` (the sweep itself).

| step | command | result |
|---|---|---|
| before | `ruff format --check .` | 207 would be reformatted (200 `.py`, 7 `.md`) |
| 1 | `ruff format .` | 206 reformatted |
| 2 | `ruff check . --select I001 --fix` | 64 files, ruff's own safe fix |
| 3 | `ruff format .` again | 0 further changes — the two passes are order-independent |
| after | `ruff format --check .` | **1397 already formatted, 0 would be reformatted** |

`ruff format` formats python fences inside Markdown, which is why 7 `.md` files were in
scope and why the sweep needed a prerequisite commit (§1.2).

### 1.1 Why the import sort is in a formatting sweep

`ruff format .` alone left the ratchet refusing, and both refusals **pre-dated the sweep** —
identical when measured at `8e8c0b3` before it:

```
LINT REGRESSION  rule=I001  tree=packages/mainline-*  baseline=0   measured=3  [HARD GATE]
LINT REGRESSION  rule=I001  tree=tests/               baseline=57  measured=58
```

Getting under the `tests/` ceiling needed exactly one file sorted. Choosing one file to buy
a number is the behaviour a ratchet exists to prevent, so I001 was driven to **0 in every
tree** instead. It now has an implicit baseline of 0 everywhere and is a hard gate the next
time it fires.

### 1.2 The one line in the sweep that a tool did not write

`docs/STATE-OF-THE-BUILD.md` §3.1 quotes `packages/trappoint-conformance/cases/_world.py`
lines 396–398 byte-for-byte, inside a ` ```python ` fence. Those three lines are a
**fragment of an argument list**, not a module, and the formatter rewrites them:

```
-"INSERT INTO {s}.clause_version "     the trailing space is what separates the table
+"INSERT INTO {s}.clause_version"      name from the column list
+
-"VALUES (%s, %s, %s, %s, %s)",        and the fragment's trailing comma becomes a
+("VALUES (%s, %s, %s, %s, %s)",)      one-tuple that is not in the source
```

After that the document attributes to `_world.py:394` text `_world.py` does not contain,
and the SQL it displays would not parse. The fence was retagged ` ```text ` in `f229c1b`,
**before** the sweep, so the sweep itself stayed pure machine output. The block is quoted
evidence, not code this repository owns.

### 1.3 What the ratchet recorded

`qa/ruff-ratchet.json`, re-taken with `--update`, which only ever writes downwards:

| metric | before | after |
|---|---|---|
| lint findings | 785 | **671** |
| unformatted files | 207 | **0** (every tree) |
| rule/tree entries tightened | — | 32, none raised |

All 21 load-bearing families remain hard-gated at 0 for `packages/trappoint-*`, and both
declared-debt entries remain at their true counts (`T201` 8, `S608` 4) rather than waived.

### 1.4 Verified

```
ruff format --check .                        0 files would be reformatted
scripts/qa/ruff_ratchet.py                   exit 0, no rule/tree count increased
pytest tests/release/test_ruff_ratchet.py    15 passed
```

and on a real run — `ci` **31462708400**, job `ruff format · the counted lint ratchet`:
**success**.

### 1.5 A lane the sweep improved without being asked

`boundary`'s `mainline-boundary unit tests` job runs a HARD `ruff check
packages/mainline-boundary tests/boundary` — no ratchet, zero tolerance.

```
8e8c0b3 (before)  Found 7 errors
47f8aa2 (after)   Found 2 errors
```

The five that went were four `I001` and one `E501`. The two survivors both pre-date the
sweep and are named in `docs/CI-STATE.md`.

---

## 2. Sweep two — finish the REUSE 3.3 migration — **NOT LANDED**

The brief was: rewrite every remaining bare `SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2` to
`LicenseRef-FSL-1.1-ALv2`, delete `LICENSES/FSL-1.1-ALv2.txt`, and gate
`non_spdx_spelling.FSL-1.1-ALv2` at 0.

**All of that works. It is also not a mechanical sweep, and it should not be done as one.**

### 2.1 It was built, measured, and reverted

The migration was performed in full on a scratch worktree, driven by `check_reuse.py`'s own
parser so that only the occurrence which RESOLVES a licence was touched — never prose:

```
resolve to FSL-1.1-ALv2:  header 1183   sidecar 71   REUSE.toml 0
bare-spelling headers in the window: 1260  (1183 files + 77 sidecars)
carry a bare header but do NOT resolve to it: 0
-> rewrote 1260 headers; every changed line was an SPDX-License-Identifier line
```

Afterwards the checker was clean and the gate was real:

```
$ scripts/qa/check_reuse.py
OK — 7310 tracked files, 0 uncovered, 3 licence texts, no counted number rose.
   improved  metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=0
   improved  metric=distinct_identifiers           baseline=4    measured=3

$ scripts/qa/check_reuse.py --self-test
7 of 7 scenarios behaved as declared.

# with one bare spelling planted back:
REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=0 measured=1
                  [HARD GATE: baseline is 0]                          exit 1
```

### 2.2 Then the same tree was run against the tests

```
$ pytest <the seven suites that name the spelling> --crdb=none
before the migration    5 failed, 326 passed, 129 skipped
after  the migration   64 failed, 267 passed, 129 skipped
```

**59 new failures.** The 5 pre-existing are declared PL-2 reds. The 59 are not, and they
fall into three families that no amount of care in the rewrite avoids:

1. **The bare spelling is asserted.** Header-lint tests require migration SQL to carry it
   verbatim — `tests/integration/schema/test_mi_views.py:323`,
   `test_mi_boundary_override.py:413`, `test_mi_clause_version_bloodline.py:240`,
   `tests/integration/algorithms/cbm/test_cbm_migration_shape.py:109`,
   `tests/integration/recall_schema/test_rc00_migration_shape.py:189`.

2. **The bare spelling is generated.** Eleven sites *emit* it into files they write —
   `scripts/custody/check_chain_fn_matches_spec.py:1021` (`banner = "-- SPDX-License-
   Identifier: FSL-1.1-ALv2\n-- rendered; do not edit"`), five `mainline-corpus` renderers,
   `verticals/mainline/apps/console/scripts/gen-types.ts:369`, `scripts/mi_ratchet.py:1611`
   and others. Migrating the fixtures without the generators means the next regeneration
   re-introduces the bare spelling and trips the new hard gate.

3. **The bare spelling is hashed.** 290 of the rewritten files are
   `verticals/mainline/db/migrations/*.sql`, whose bytes are recorded in
   `verticals/mainline/db/migrations.lock.json`.
   `packages/trappoint-migrate/tests/test_lockfile.py::test_the_committed_manifest_is_current`
   fails immediately. **That lockfile is the artefact behind the project's central claim,
   `chain 271/271 applied, 0 failed`.**

### 2.3 The ruling

A change that rewrites 290 hashed migration files, regenerates the manifest that the
central claim is measured from, and rewrites eleven generators, is not a formatting sweep
that lands unreviewed at the end of a wave. It is its own wave, and it needs the chain
re-proved against a live node afterwards. Landing it here to turn one CI job green, two
days before submission, would have traded a counted and honest number for an unproven one.

`qa/reuse-ratchet.json` therefore still records `non_spdx_spelling.FSL-1.1-ALv2 = 1213`
against a measured 1254, `ci`'s `REUSE` job stays red, and `submission` stays red with it.
**That red is untidy, not intentional** — it is a fixable thing this worker chose not to
fix badly. `docs/CI-STATE.md` says so in those words.

### 2.4 What the next wave should do, in order

1. Migrate the **eleven generators** first, and regenerate their artefacts.
2. Migrate the **five assertion sites** to expect `LicenseRef-FSL-1.1-ALv2`.
3. Migrate the **1 183 headers and 77 sidecars** with the resolver-driven rewrite (never a
   global search-and-replace: five files name the bare spelling as data in order to assert
   something about it, and counting a guard as an offence is how a guard gets deleted).
4. Regenerate `migrations.lock.json` and **re-prove the chain against a live node**, quoting
   `chain N/N applied` in the commit message.
5. Delete `LICENSES/FSL-1.1-ALv2.txt`, re-take the baseline, and confirm the metric records
   `0` — which under this checker's own rule is a hard gate from then on.
6. Update the two published censuses (`docs/submission/LICENCE-CENSUS.md`,
   `docs/submission/LICENSING.md`), whose quoted numbers
   `tests/release/test_check_reuse.py::test_the_census_document_quotes_the_published_baseline`
   checks against the baseline, and rewrite
   `test_the_published_baseline_publishes_the_two_spellings`, which today asserts
   `gated[bare] > 0` — "a divergence recorded at 0 would mean it had been repaired".
   It will have been.
