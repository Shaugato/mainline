<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# LICENCE CENSUS — the counted version

**Every number on this page was produced by `python3 scripts/qa/check_reuse.py` against the
working tree at `D:/CoackroachDBxAWS/mainline` on 2026-08-10T05:57:34Z, and is stored in
`qa/reuse-ratchet.json`.** Nothing here was typed by hand. `tests/release/test_check_reuse.py`
fails if this page and that artefact stop agreeing, so a stale table is a red build rather
than a quiet lie.

This page is the *count*. `docs/submission/LICENSING.md` is the *policy* — which tree is
under which licence and why. Read that one if the question is "may I fork this".

> ## ⚠ RE-RUN 2026-08-14 · THE COVERAGE CENSUS HAS MOVED, THE RATCHET HAS NOT, AND THE
> ## SELF-TEST HAS A RED CELL THIS PAGE PRINTS AS GREEN
>
> `.venv/Scripts/python.exe scripts/qa/check_reuse.py`, RAN 2026-08-14, exits **0** —
> *"7576 tracked files, 0 uncovered, 4 licence texts, no counted number rose"*. **The gate is
> green.** Everything below is nevertheless out of date, and one paragraph of it is wrong.
>
> **1 · The §1 and §2 tables are from 2026-08-10 and describe a smaller tree.** They are not
> re-typed here, because `qa/reuse-ratchet.json` is the artefact this page transcribes and
> `--write` is the only thing entitled to re-take the snapshot — a command this documents wave
> does not run. Today's live totals, for comparison:
>
> | | 2026-08-10 (§1, the artefact) | **2026-08-14 (live)** |
> |---|---:|---:|
> | tracked files | 7 120 | **7 576** |
> | header | 2 250 | **2 531** |
> | sidecar | 172 | **199** |
> | `REUSE.toml` | 4 518 | **4 636** |
> | exempt | 180 | **210** |
> | **UNCOVERED** | **0** | **0** |
> | `LicenseRef-FSL-1.1-ALv2` resolved | 4 773 | **4 890** |
> | `FSL-1.1-ALv2` resolved | 1 213 | **1 213** |
> | `Apache-2.0` resolved | 886 | **999** |
> | `CC-BY-4.0` resolved | 68 | **264** |
>
> **`UNCOVERED` is 0 in both readings and in every directory** — that is the gated number and
> it did not move. **`FSL-1.1-ALv2` is 1 213 in both** — that is the falling-only divergence
> counter and it did not rise, which is the whole point of §3. `census` figures move with the
> ordinary life of the tree and are recorded, never gated, exactly as §3 says.
>
> **2 · §4 is out of date in the good direction.** *"Five globs that match nothing"* is now
> **one**: `#4:packages/**/*.jsonl`, the deliberately defensive pattern. `LICENSE`,
> `docs/submission/**`, `evidence/provenance/**` and `evidence/tool-usage/**` are all tracked
> now, exactly as §4 predicted they would be — *"four of the five are not dead, they are
> waiting on a `git add`"*. §5's parenthetical is likewise closed: `exempt by declared policy`
> now prints `REUSE.toml` (1), not 0.
>
> **3 · §7's table is WRONG about the GREEN control, and this is the one correction that is
> not just arithmetic.** That table shows all seven `--self-test` scenarios passing. RAN
> 2026-08-14:
>
> ```
> --self-test — one synthetic repository, one planted violation per family
> scenario                               expect  exit  result   why it is here
> GREEN control                            pass     0  FAILED   a complete tree passes; a checker that always refuses is broken, not safe
> no header, no sidecar, no annotation   REFUSE     1  ok       the file nobody licensed
> identifier with no text in LICENSES/   REFUSE     1  ok       a licence named but not shipped
> orphan text in LICENSES/               REFUSE     1  ok       a licence shipped but not used
> REUSE.toml glob matching nothing       REFUSE     1  ok       a map with a road to nowhere
> a counted number above the ratchet     REFUSE     1  ok       the divergent spelling grows by one
> --write on a broken tree               REFUSE     1  ok       regeneration raises a number; it must never launder a broken one
> 1 of 7 scenarios did not behave as declared.
> ```
>
> Exit **1**. `python -m pytest tests/release/test_check_reuse.py` agrees: **2 failed, 31
> passed, 1 error**, all three in the self-test.
>
> **The six refusal scenarios still fire. The one that broke is the GREEN control** — the
> scenario whose entire job is to prove the checker is not simply refusing everything. §7's
> own sentence, which is correct and is why this matters, reads: *"The GREEN control is not
> decoration: a checker that refuses everything is broken, not safe."* **A checker whose green
> half is red cannot support the sentence "0 uncovered" as strongly as this page claims it
> can**, even though the production run over the real tree exits 0 and 0 is very probably
> right.
>
> This is a defect in `scripts/qa/check_reuse.py` or in its synthetic fixture, not in this
> page's tables, and **neither the checker nor `tests/release/test_check_reuse.py` is this
> document's to edit** — and neither may be relaxed to obtain a green. **Raised as a
> cross-domain finding, and added to §8.**
>
> **4 · This file's own NAME is a false positive in another scanner.** `provenance_census.py`
> classifies `docs/submission/LICENCE-CENSUS.md` as a *foreign licence file* — its filename
> matches `^(LICEN[CS]E|…)([._-]…)?$` — and therefore reports `bundles_third_party_code: true`
> for the whole repository. The file is ours and carries this project's SPDX copyright.
> **It is not renamed to make a scanner quieter.** `docs/submission/DISCLOSURE.md` §4 carries
> the finding, the line numbers and the one honest repair.

---

## 0 · The sentence this page exists to make false

`docs/HONESTY.md`, section **"Ratchets that do not exist yet"**, says of licence coverage:

> `qa/reuse-ratchet.json` is not [on disk]. Licence-header compliance is therefore an
> *uncounted* number in this document. […] No committed artefact re-derives the header
> census, so this page refuses to print a figure for it.

**Licence-header compliance was an UNCOUNTED number in `docs/HONESTY.md` until this ratchet
landed.** It is counted now: `qa/reuse-ratchet.json` is on disk, `scripts/qa/check_reuse.py`
re-derives every figure below in 9.14 s wall on this machine from `git ls-files -z` and the
standard library, and each figure is addressable in the citation form `docs/HONESTY.md` uses
— for example `[src: qa/reuse-ratchet.json#counted.uncovered_total]`. Updating that section
belongs to the owner of `docs/HONESTY.md`, not to this page; it is raised as a cross-domain
note and deliberately not edited here.

The same section's second paragraph — *"`scripts/qa/check_reuse.py` is not one of the files
on disk, and every substantive job declares `needs: [checkers]`. The pipeline still cannot
start"* — is also now false. The file is on disk at the path `.github/workflows/ci.yml`
names, and the `checkers` registry loop reports `missing=0` over all five entries.

---

## 1 · Coverage, by top-level directory

Every tracked file resolves exactly one licence, by one of three mechanisms, or it is
exempt. **0 files are uncovered**, and that 0 is gated per directory as well as in total,
so coverage cannot regress in one corner while the total is carried by another.

| directory | files | header | sidecar | REUSE.toml | exempt | UNCOVERED |
|---|---:|---:|---:|---:|---:|---:|
| `.claude-plugin` | 2 | 0 | 1 | 0 | 1 | 0 |
| `.github` | 17 | 17 | 0 | 0 | 0 | 0 |
| `.hypothesis-corpus` | 2 | 2 | 0 | 0 | 0 | 0 |
| `<root>` | 16 | 10 | 1 | 4 | 1 | 0 |
| `LICENSES` | 2 | 0 | 0 | 0 | 2 | 0 |
| `docs` | 36 | 26 | 0 | 10 | 0 | 0 |
| `evidence` | 30 | 7 | 10 | 3 | 10 | 0 |
| `infra` | 26 | 11 | 0 | 15 | 0 | 0 |
| `mine_templates` | 1 | 1 | 0 | 0 | 0 | 0 |
| `out_mainline` | 2 | 2 | 0 | 0 | 0 | 0 |
| `out_trappoint_ref` | 2 | 2 | 0 | 0 | 0 | 0 |
| `packages` | 643 | 560 | 26 | 31 | 26 | 0 |
| `qa` | 4 | 1 | 0 | 3 | 0 | 0 |
| `scripts` | 20 | 20 | 0 | 0 | 0 | 0 |
| `skills` | 15 | 11 | 2 | 0 | 2 | 0 |
| `spec` | 40 | 36 | 2 | 0 | 2 | 0 |
| `tests` | 587 | 446 | 29 | 83 | 29 | 0 |
| `verticals` | 5675 | 1098 | 101 | 4369 | 107 | 0 |
| **TOTAL** | **7120** | **2250** | **172** | **4518** | **180** | **0** |

`2250 + 172 + 4518 + 180 = 7120`. The `exempt` column is 178 `.license` sidecar files plus
the 2 licence texts in `LICENSES/`; REUSE Specification 3.3 exempts both classes by name,
because a sidecar *is* licensing information rather than a thing that needs some, and a
licence text is not licensed material.

**`verticals/` is 80% of the tree and 97% of the REUSE.toml column.** 4 369 of its 5 675
files are replay fixtures, recorded request/response frames and captured SQL transcripts
that are byte-addressed by the console loader and by the fixity checker. Not one of them
may gain a header without breaking a digest, which is exactly the case `REUSE.toml` exists
to serve.

---

## 2 · Four censuses of the same tree, and how they reconcile

A licence census is not one number, and quoting one number without its method is how two
honest measurements end up looking like a contradiction. `qa/reuse-ratchet.json` records
all four.

### 2.1 · Occurrences, `[^ ]*` — the number the plan quotes

```
$ git grep -h -o -E "SPDX-License-Identifier: [^ ]*" | sed 's/.*: //' | sort | uniq -c | sort -rn
   1167 FSL-1.1-ALv2
    782 Apache-2.0
    375 LicenseRef-FSL-1.1-ALv2
     63 FSL-1.1-ALv2",
     49 CC-BY-4.0
      7 CC-BY-4.0",
```

`[src: qa/reuse-ratchet.json#census.identifier_occurrences.token]`. This counts
**occurrences anywhere in a file**, so it also counts the tag inside a Python string
literal — which is what the `FSL-1.1-ALv2",` bucket is. That is why it is recorded and
never gated: writing a test fixture containing the string would otherwise be a red build.

### 2.2 · Occurrences, `.*` — the same command, one character different

```
$ git grep -h -o -E "SPDX-License-Identifier: .*" | sed 's/.*: //' | sort | uniq -c | sort -rn
   1163 FSL-1.1-ALv2
    742 Apache-2.0
    375 LicenseRef-FSL-1.1-ALv2
     63 FSL-1.1-ALv2",
     49 CC-BY-4.0
     32 Apache-2.0 #}
      8 Apache-2.0 -->
      4 FSL-1.1-ALv2 -->
```

1 163, not 1 167. The four missing bare-FSL headers are the ones that sit inside an HTML
comment and end ` -->`; `[^ ]*` stops at the space and folds them back in, `.*` runs to end
of line and buckets them separately. **`1163 + 4 = 1167`** and
**`742 + 32 + 8 = 782`**, exactly. Neither reading is wrong and neither was adjusted to
match the other. `LicenseRef-FSL-1.1-ALv2` is 375 under both.

### 2.3 · Headers, per file

One count per file: the **first** match in the **first 4 KiB**, over every tracked file
including the 178 sidecars.

| identifier | headers | of which sidecar files | covered-file headers |
|---|---:|---:|---:|
| `FSL-1.1-ALv2` | 1219 | 76 | 1143 |
| `Apache-2.0` | 781 | 56 | 725 |
| `LicenseRef-FSL-1.1-ALv2` | 374 | 36 | 338 |
| `CC-BY-4.0` | 54 | 10 | 44 |
| **total** | **2428** | **178** | **2250** |

The right-hand column is the `header` column of §1. 4 KiB and not "the whole file" is a
deliberate choice: the root `LICENSE` is the Apache Software Foundation's own text, and
that text quotes `SPDX-License-Identifier: Apache-2.0` inside its appendix boilerplate
about 11 KiB in. A parser that reads whole files concludes the Apache licence *text* is a
file licensed under Apache-2.0. A header is a header because of where it is.

### 2.4 · Resolved, after precedence — the licence each file is actually under

| identifier | header | sidecar | REUSE.toml | total |
|---|---:|---:|---:|---:|
| `LicenseRef-FSL-1.1-ALv2` | 338 | 36 | 4399 | 4773 |
| `FSL-1.1-ALv2` | 1143 | 70 | 0 | 1213 |
| `Apache-2.0` | 725 | 56 | 105 | 886 |
| `CC-BY-4.0` | 44 | 10 | 14 | 68 |
| **total** | **2250** | **172** | **4518** | **6940** |

`7120 − 180 exempt = 6940`. `[src: qa/reuse-ratchet.json#census.identifiers_resolved]`.

**178 sidecar files, 172 sidecar-resolved licences.** The six-file difference is not a
defect and is not rounding: six files carry a header *and* a sidecar, and REUSE's default
`precedence = "closest"` gives the header the last word. All six, named:

```
verticals/mainline/apps/console/tests/unit/a11y/fixtures/planted/clean.css.fixture.license
verticals/mainline/apps/console/tests/unit/a11y/fixtures/planted/clean.tsx.fixture.license
verticals/mainline/apps/console/tests/unit/a11y/fixtures/planted/memory-person.tsx.fixture.license
verticals/mainline/apps/console/tests/unit/a11y/fixtures/planted/notes.css.fixture.license
verticals/mainline/apps/console/tests/unit/a11y/fixtures/planted/violations.css.fixture.license
verticals/mainline/apps/console/tests/unit/a11y/fixtures/planted/violations.tsx.fixture.license
```

### 2.5 · The same numbers, re-derived in SQL on the local node

A number produced only by the program that wants it to be right is not a measurement. The
checker's per-file verdicts were loaded into CockroachDB CCL v26.2.5 on the pinned local
node (`postgresql://root@localhost:26257`, database `w_s02_reuse_checker`) and the census
was re-derived by `GROUP BY` rather than by Python `Counter`:

```sql
CREATE TABLE file_licence (
  path        STRING PRIMARY KEY,
  resolved_by STRING NOT NULL,
  licence     STRING NULL,
  top_dir     STRING NOT NULL);
SELECT resolved_by, count(*) FROM file_licence GROUP BY 1 ORDER BY 2 DESC;
SELECT licence, count(*) FROM file_licence WHERE licence IS NOT NULL GROUP BY 1 ORDER BY 2 DESC;
SELECT top_dir, count(*) FROM file_licence WHERE resolved_by = 'uncovered' GROUP BY 1;
```

```
rows loaded : 7120

-- how each tracked file resolves a licence
  reuse_toml             4518
  header                 2250
  exempt_sidecar_file     178
  sidecar                 172
  exempt_licence_text       2

-- the licence every non-exempt tracked file ends up under
  LicenseRef-FSL-1.1-ALv2      4773
  FSL-1.1-ALv2                 1213
  Apache-2.0                    886
  CC-BY-4.0                      68

-- the non-SPDX spelling, the number the ratchet gates: 1213
-- UNCOVERED per top-level directory: none - 0 in every directory
-- distinct paths: 7120

SQL == qa/reuse-ratchet.json#census.identifiers_resolved : True
SQL == qa/reuse-ratchet.json#counted.non_spdx_spelling   : True
SQL == qa/reuse-ratchet.json#census.tracked_files        : True
```

`path STRING PRIMARY KEY` is doing work here rather than decorating: the load would fail on
a duplicate, so "every tracked file resolves **exactly one** licence" is asserted by the
database rather than trusted from the loader. 7 120 rows went in and 7 120 distinct paths
came out.

### 2.6 · The same numbers, derived twice by two programs that share no code

`docs/submission/LICENSING.md` §5 loaded the map into CockroachDB v26.2.5 on the local node
and re-derived it in SQL from `git ls-files` and a separately written `REUSE.toml` parser.
It reports `header 2250 · sidecar 172 · sidecar_itself 178 · reuse_toml 4518 ·
licence_text 2`, and `LicenseRef-FSL-1.1-ALv2 4773 · FSL-1.1-ALv2 1213 · Apache-2.0 886 ·
CC-BY-4.0 68`. **Every one of those ten figures is the figure this checker produces**, and
neither program was written against the other's output. Two independent derivations
agreeing is the strongest statement on this page.

---

## 3 · The two spellings, and what is gated

`FSL-1.1-ALv2` is **not** on the SPDX licence list, so REUSE Specification 3.3 requires the
`LicenseRef-` form. This tree uses both. Ruling **L-1** (`docs/leads/submission-plan.md`)
decided not to repair that by rewriting headers: the edit would touch files owned by all
eight build domains simultaneously and is forbidden by the ownership rule. Instead both
filenames ship in `LICENSES/` holding byte-identical text, the checker accepts either as
satisfying either, and **the divergence is published as a number that may fall and may not
rise**:

```json
"counted": {
  "non_spdx_spelling": { "FSL-1.1-ALv2": 1213 }
}
```

1 213 files are licensed under the non-conforming spelling today. That figure may go down.
It cannot go up: a new file carrying `SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2` makes
`python3 scripts/qa/check_reuse.py` exit 1, and the only way to raise it is
`--write`, which leaves the increase in a diff a reviewer has to approve.

The **gated** number is the resolved count (1 213), not the occurrence count (1 167),
because the resolved count is the number of files actually *licensed* under the
non-conforming spelling. The occurrence census also counts the string where it appears
inside source code, and a lint that reddens when someone writes a test fixture is a lint
people learn to ignore.

### Everything else that is gated

| counted metric | today | what a rise would mean |
|---|---:|---|
| `uncovered_total` | 0 | a file that names no licence at all — hard gate |
| `uncovered_by_top_level_directory` | 0 × 18 | the same, per directory, so no corner can regress silently |
| `identifiers_without_licence_text` | 0 | a licence named by a file and not shipped in `LICENSES/` |
| `unreferenced_licence_texts` | 0 | a licence shipped in `LICENSES/` that nothing uses |
| `orphan_sidecars` | 0 | a `.license` sidecar beside a file that no longer exists |
| `unreadable_files` | 0 | a path the checker could not open — Windows `MAX_PATH`, most likely |
| `reuse_toml_patterns_matching_nothing` | 5 | a new glob in `REUSE.toml` that covers nothing |
| `distinct_identifiers` | 4 | a fifth licence entering the tree, which should be deliberate |
| `non_spdx_spelling.FSL-1.1-ALv2` | 1213 | the divergence growing |

A metric absent from the baseline defaults to 0, so a category that has never fired is
gated at 0 too. `census`, by contrast, is recorded and printed and **not** gated: those are
coverage totals that move in both directions with the ordinary life of the tree, and gating
`tracked_files` would make adding a file a red build.

---

## 4 · The five globs that match nothing, and which kind each is

```
#0:LICENSE                  <- matches 1 file(s) that exist but are NOT tracked; `git add` revives it
#4:packages/**/*.jsonl      <- matches nothing on disk either
#6:docs/submission/**       <- matches 6 file(s) that exist but are NOT tracked; `git add` revives it
#6:evidence/provenance/**   <- matches 2 file(s) that exist but are NOT tracked; `git add` revives it
#6:evidence/tool-usage/**   <- matches 5 file(s) that exist but are NOT tracked; `git add` revives it
```

"Five dead globs" would be a true sentence that misleads. **Four of the five are not dead,
they are waiting on a `git add`** — including `LICENSE` itself, the Stage One blocker,
which exists on disk and is not yet tracked. Each falls out of this count the moment the
file it names is committed, and the ratchet permits a fall. Only
`packages/**/*.jsonl` matches nothing anywhere; it is a defensive pattern written so that
narrowing the block above it cannot silently drop a file class.

---

## 5 · The one exemption, declared rather than assumed

`REUSE.toml` itself carries no licence. It declares `SPDX-License-Identifier` as a TOML
assignment *for other files*, it has no header of its own, and none of its own
`[[annotations]]` tables matches its own path. REUSE Specification 3.3 exempts the
`LICENSES/` directory and `.license` files **by name** and does not name `REUSE.toml`, so
this checker will not claim the spec exempts it.

It is exempted **by declared policy**, in `qa/reuse-ratchet.json` under
`policy.exempt_paths`, with the reason written next to it. The exemption is printed on
every run, recorded in `census.exempt_by_policy`, and refused as `[STALE-EXEMPTION]` the
day the path it names leaves the tree. The repair is a three-line `[[annotations]]` block
in `REUSE.toml` — a file this checker's owner does not own, so it is a cross-domain note
and not a silent pass.

*(`census.exempt_by_policy` reads 0 rather than 1 in the snapshot above for the same reason
`#0:LICENSE` is listed as dead: `REUSE.toml` is on disk and not yet tracked, so
`git ls-files` does not see it. It becomes 1 the moment it is committed.)*

---

## 6 · Re-derive every number on this page

One command, from the repository root. No arguments, standard library only, no network —
which is what the `reuse` job in `.github/workflows/ci.yml` runs under harden-runner with
egress blocked.

```bash
python3 scripts/qa/check_reuse.py
```

It prints the §1 table, the §2.3/§2.4 identifier table, the §4 glob list and the §5
exemption, then exits 0 if and only if nothing is uncovered, every identifier has a text,
no text is unreferenced, and no counted number has risen.

```bash
# the full artefact, including everything this page quotes
python3 scripts/qa/check_reuse.py --json

# regenerate the baseline — the ONLY way a counted number rises
python3 scripts/qa/check_reuse.py --write

# prove the checker is capable of refusing (see §7)
python3 scripts/qa/check_reuse.py --self-test
```

Independent of the checker, the §2.1 and §2.2 censuses are two shell one-liners:

```bash
git grep -h -o -E "SPDX-License-Identifier: [^ ]*" | sed 's/.*: //' | sort | uniq -c | sort -rn
git grep -h -o -E "SPDX-License-Identifier: .*"    | sed 's/.*: //' | sort | uniq -c | sort -rn
```

---

## 7 · The red half

A lint that has never been red asserts nothing, so `--self-test` builds a complete
synthetic repository in a temporary directory, proves the checker **passes** it, then plants
one violation at a time and requires a refusal for each:

```
scenario                               expect  exit  result
GREEN control                            pass     0  ok
no header, no sidecar, no annotation   REFUSE     1  ok
identifier with no text in LICENSES/   REFUSE     1  ok
orphan text in LICENSES/               REFUSE     1  ok
REUSE.toml glob matching nothing       REFUSE     1  ok
a counted number above the ratchet     REFUSE     1  ok
--write on a broken tree               REFUSE     1  ok
```

The GREEN control is not decoration: a checker that refuses everything is broken, not safe.

`--self-test` was itself run against five deliberately neutered copies of the checker before
this page was written, and each planted violation was observed **failing alone** when its
own assertion was removed — the five runs and their verbatim output are recorded in the
docstring of `tests/release/test_check_reuse.py`.

---

## 8 · What is still open

Recorded here rather than in a commit message, in the manner of `docs/HONESTY.md`.

| open | detail |
|---|---|
| 1 213 files under a non-SPDX identifier | Mitigated by the alias texts and published as a gated count. Not repaired. It must reach 0. |
| `docs/HONESTY.md` still says this ratchet does not exist | True when it was written, false now. Not edited here: that file has an owner and this one does not. Raised as a cross-domain note with the exact `[src: …]` pointers to use. |
| `qa/reuse-ratchet.json` is not a declared evidence *family* | `tests/release/test_honesty_is_checkable.py` carries a `FAMILIES` table that forces `docs/HONESTY.md` to cite an artefact once it lands. This ratchet is not in it, so nothing yet compels the citation. Adding the family and the citation must happen in one change, or that test goes red. |
| the census is a snapshot taken mid-wave | Ten workers were writing to this tree. `census` figures are re-derived live on every run and go stale in the JSON the instant a file lands; they are recorded, never gated. Re-take once on the merge commit with `--write`. |
| `LICENSE`, `REUSE.toml` and two of the four texts in `LICENSES/` are untracked | They exist on disk and are not committed, which is why four globs read as dead and `exempt_by_policy` reads 0. Not this worker's commit to make. **CLOSED 2026-08-14** — all four are tracked; the dead-glob count fell 5 → 1 and `exempt_by_policy` reads 1. |
| **`check_reuse.py --self-test`'s GREEN control FAILS** | **Opened 2026-08-14.** Six of seven scenarios behave as declared; the seventh — the one asserting a complete synthetic tree *passes* — does not, so `--self-test` exits 1 and `tests/release/test_check_reuse.py` reports 2 failed / 31 passed / 1 error. The production run over the real tree still exits 0 with `0 uncovered`. §7's table above is a record of an older run and is annotated rather than re-typed. **The checker and the test are not this page's to edit, and neither may be relaxed to obtain a green.** Owner: the quality domain. |
| `qa/reuse-ratchet.json` records a 7 120-file tree and the tree is 7 576 | The `census` block goes stale by design — it is recorded, not gated — and only `--write` re-takes it. A documents wave does not run `--write`. The gated numbers (`uncovered_total` 0, `non_spdx_spelling` 1 213) are unmoved. Re-take once on a merge commit. |
| `docs/submission/LICENCE-CENSUS.md` is read as a *foreign licence file* by `provenance_census.py` | Its filename matches that scanner's licence-file pattern and the holder it reads — ours — is never tested, so `bundles_third_party_code` flips true for the whole repository. **Not repaired by renaming this file.** Cross-domain finding; `DISCLOSURE.md` §4 carries it. |
