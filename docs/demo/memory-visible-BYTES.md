<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MEMORY-VISIBLE — the byte record

**Worker:** `w5-bytes` · **Date:** 2026-08-15 · **Repo:** `D:/CoackroachDBxAWS/mainline`, HEAD `4af05e1`
**Plan:** `docs/demo/memory-visible-plan.md`, ruling **R-M2** · **Deliverables:**
`verticals/mainline/apps/console/scripts/check-memory-bytes.ts`,
`tests/deploy/test_memory_page_is_served.py`, this file.

Every number below was measured on this workstation on **2026-08-15**, with the command that
reproduces it printed beside it. Nothing here is copied from another document, and where a
figure in another document has gone stale that is said out loud rather than quietly matched.

---

## 0 · The verdict, in one paragraph

R-M2 rules that the memory panel's four files in `console/public/` add **zero bytes** to the
console entry closure, because Vite copies `public/` verbatim and never writes it into
`dist/.vite/manifest.json`, which is the only thing `scripts/check-budgets.ts` reads.
**Measured, over two full builds of the same tree with `public/` moved aside and then put
back: the entry closure is byte-identical — same chunk names, same sha256, same gzip length,
same total.** The four files are served as their own objects, the largest of them at
**16,023 B** on the wire against a **139,264 B** ceiling, leaving **123,241 B** of headroom on
that object. `DEFAULT_MAX_RESPONSE_BYTES` is unchanged at `136 * 1024`; `vite.config.ts`,
`budgets.json` and `REUSE.toml` were **not edited by `w5-bytes`** (the first two are modified
in this tree by the operator-systems plan — §10 says exactly how, and why R-M2 survives it);
nothing was committed.

**`pnpm run ci` is not green, and this record does not round that off.** Three of its seven
steps are red, plus two QA ratchets outside it, and §8–§9 measure and attribute every one.
Two are caused by the memory panel and neither can be fixed from a file `w5-bytes` owns:

* `pnpm run check:entrypoints` refuses `dist/memory.html` as a stale leftover. It is not
  stale — it is the `publicDir` copy R-M2 requires — and the refusal comes from a script the
  operator-systems plan added. Attributed by measurement in §8.2, with the one-predicate fix
  written out.
* `pnpm run lint` reports a parse error on `public/memory-loop.js` and
  `public/memory-verify.js`, because `eslint.config.js` applies type-aware linting to every
  `.js` in the tree and `public/` is in no `tsconfig`. §8.1.

The rest belong elsewhere: `pnpm run test` fails one operator a11y case out of 2,503, and
`pnpm run lint`'s remaining 12 errors split into 1 that is red at HEAD `4af05e1` and 11 that
arrived with the operator plan. Both QA ratchets — `check_reuse` and `ruff_ratchet` — were
already refusing before this plan started, and §8.1, §8.4 and §9 prove that from HEAD rather
than assert it. **Nothing was worked around: no `continue-on-error`, no `|| true`, no rule
disabled, no ratchet rebaselined, no other worker's file edited.**

---

## 1 · The environment the numbers came from

| | |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.13.14 · zlib `1.3.1` (stock) |
| Node | v24.14.0 · zlib `1.3.1-e00f703` (Chromium's zlib fork) |
| pnpm | 11.5.3 |
| Vite | 7.1.12 |
| Ceiling | `static_site.DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024 = 139,264` — **read from the module on every run, never restated** |
| Floor | `test_static_site.py::_MINIMUM_HEADROOM_BYTES = 1,024` — read the same way |

The two zlibs are the same version number and **do not produce the same bytes**: Node bundles
Chromium's fork. §6 measures the disagreement rather than rounding it away.

---

## 2 · Reproducing every number here

```
# the before/after entry-closure proof, and the per-file line item   (~10 s, builds twice)
cd verticals/mainline/apps/console
node scripts/check-memory-bytes.ts

# the serving proof, the packer-exact compression, and the ceiling falsification
cd D:/CoackroachDBxAWS/mainline
.venv/Scripts/python.exe -m pytest tests/deploy/test_memory_page_is_served.py --crdb=none -q

# the licence census
.venv/Scripts/python.exe scripts/qa/check_reuse.py

# the console gate chain
cd verticals/mainline/apps/console && pnpm run ci
```

`check-memory-bytes.ts` leaves `dist/` exactly as a plain `vite build` leaves it: its second
build is an ordinary one, with `public/` in place.

---

## 3 · The entry closure — before and after, byte for byte

`node scripts/check-memory-bytes.ts`, 2026-08-15. Two full builds, back to back, the first
with `public/` renamed to `.public-bytes-probe/` and the second with it restored.

```
  built  WITHOUT public/              3.8s
  built  WITH public/                 3.8s

  ENTRY CLOSURE — byte-identical is the whole claim
    SAME  index.html     assets/index-Dif0ht5g.js     490,200 B identity   137,903 B wire  headroom     1,361 B
    SAME  operator.html  assets/operator-D24tzVGh.js   96,734 B identity    29,890 B wire  headroom   109,374 B
    total  5 files, 179,645 B gzipped (unchanged: yes)
    keys   35 manifest keys without public/, 35 with (identical set: yes)
```

| | without `public/` | with `public/` | delta |
|---|---:|---:|---:|
| `assets/index-Dif0ht5g.js` identity | 490,200 | 490,200 | **0** |
| `assets/index-Dif0ht5g.js` sha256 | `a8d61429076589ee…` | `a8d61429076589ee…` | **identical** |
| `assets/operator-D24tzVGh.js` identity | 96,734 | 96,734 | **0** |
| `assets/operator-D24tzVGh.js` sha256 | `c4e1789ac994d537…` | `c4e1789ac994d537…` | **identical** |
| entry static closure, 5 files, gzipped | 179,645 | 179,645 | **0** |
| manifest keys | 35 | 35 | **identical set**, not merely the same count |
| manifest keys or emitted paths naming a `public/` file | 0 | **0** | — |

Ten builds were run in total across five invocations of the gate while it was being written
and falsified. The entry chunk's **name, identity size and digest did not move once**, which
is also a small independent confirmation of `evidence/deploy/console-repro.json`'s
reproducibility claim on this workstation.

---

## 4 · The four files the memory panel adds, as their own line item

Identity is the file on disk. **Wire** is the `<name>.gz` sibling
`scripts/deploy/build_lambda.{sh,ps1}` writes beside every compressible `web/**` entry —
`gzip_bytes()`, level 9, MTIME 0, no FNAME — which is the representation every browser takes.
Both columns are measured against the same 139,264 B ceiling because `static_site.serve`
weighs whichever one it is about to send.

| file | identity B | wire B (CPython, the packer) | wire B (Node, the gate) | headroom on the packer figure | sha256 |
|---|---:|---:|---:|---:|---|
| `memory-loop.js` | 53,477 | **16,023** | 16,021 | 123,241 | `6957fbd3f351cf3d…` |
| `memory-verify.js` | 26,606 | **8,809** | 8,796 | 130,455 | `e4adf35d13d38bae…` |
| `memory.css` | 27,565 | **7,848** | 7,811 | 131,416 | `e16d79eb8c203bc8…` |
| `memory.html` | 35,246 | **7,990** | 7,943 | 131,274 | `e962a300822390c4…` |
| **panel total** | **142,894** | **40,670** | 40,571 | — | — |

Every file clears the ceiling on **both** representations, and by more than 123 KB on the
worst of them. The identity column matters as much as the wire column: a caller that sends no
`Accept-Encoding` is served the identity object — that is `curl` without `--compressed`, which
is how a judge checks a page by hand — and an identity object over the ceiling answers 413 to
exactly that caller. The console's own entry chunk is already in that position at 490,200 B
identity, deliberately and with the cost written down in `static_site.py`. **The memory panel
does not join it.**

The panel's whole wire cost, 40,670 B, is spread across four separate responses. It is not a
single object and it is not added to any other object, so **no response on this origin grew**.

---

## 5 · Why a `public/` file cannot enter a budget — measured, not argued

* `vite.config.ts` sets **no `publicDir`**, so Vite's default `public/` applies and is copied
  verbatim into `dist/`: not transformed, not hashed, **not written into the manifest**.
* The manifest holds **35 keys** and **not one** of them, and none of their emitted paths, is
  `memory.html`, `memory.css`, `memory-loop.js` or `memory-verify.js`.
* `check-budgets.ts` resolves every budget root through the manifest — the `entry` keyword
  selects `isEntry` chunks, a `glob:` root is matched against manifest keys, and anything else
  must equal a key exactly. A file absent from the manifest matches none of the three.

**Measured while falsifying, and worth recording because it was not obvious:** Vite copies
`publicDir` into `outDir` **before** Rollup writes the bundle. A planted
`public/assets/index-Dif0ht5g.js`, 70 B longer than the real chunk, was *overwritten by the
emitted chunk* — `dist/assets/index-Dif0ht5g.js` came out at 490,200 B, not 490,270 B. So a
`public/` file cannot displace an emitted asset even by colliding with its name. That makes
R-M2 stronger than it was written: the panel is outside the module graph, and it also cannot
reach the emitted bytes through the copy.

**One line of the plan is now stale, and it is recorded here rather than worked around.**
`memory-visible-plan.md` §1 says `budgets.json` has exactly two budget roots, `entry` and
`glob:src/features/ancestry/render3d/**`. That was true when the plan was written. The
operator-systems lead has since split `entry` into two, and the file now declares
`index.html`, `operator.html` and the `render3d` glob. **The ruling is unaffected** — all
three are still manifest lookups — so `test_no_memory_file_can_enter_a_budgets_json_root`
asserts the *property* (no root names a `public/` file; every non-glob root is a declared
build input) rather than the list. `budgets.json` was not edited.

---

## 6 · The two compressors disagree, and by how much

The gate runs under Node because only Node can drive the bundler; the packer runs under
CPython. Both call zlib 1.3.1 at level 9 with `-MAX_WBITS`, and they do not agree:

| object | CPython | Node | Node − CPython |
|---|---:|---:|---:|
| `memory.html` | 7,990 | 7,943 | **−47** |
| `memory.css` | 7,848 | 7,811 | −37 |
| `memory-loop.js` | 16,023 | 16,021 | −2 |
| `memory-verify.js` | 8,809 | 8,796 | −13 |
| `assets/index-Dif0ht5g.js` | 137,887 | 137,903 | **+16** |

Node bundles Chromium's zlib fork (`process.versions.zlib = 1.3.1-e00f703`). The differences
are tens of bytes and run in both directions.

**This is why the work is split the way it is.** The TypeScript gate uses its numbers for two
things and the calibration is irrelevant to both: *equality between two builds compressed by
the same compressor* (§3, where any consistent compressor answers the question), and an
order-of-magnitude line item where the margin is ~123,000 B. The **authoritative** per-file
sibling size is measured in CPython, with the packer's own `gzip_bytes` reproduced
byte-for-byte, by `tests/deploy/test_memory_page_is_served.py` — which then feeds the result
to the real `static_site.serve`. `test_the_sibling_this_file_writes_is_the_one_build_lambda_writes`
holds that reproduction to `build_lambda.ps1`'s own source, so it cannot drift into being a
statement about a compressor nothing deploys.

**Neither figure is the deployed one, and that is expected.** The shipped sibling is
**138,177 B** (`web/assets/index-LoN3Sn_L.js.gz`, from
`out/lambda/mainline-demo-api-arm64.zip` `sha256 7c97b532…`), built with
`MAINLINE_BUILD_ID=f0ba767` and `--console-transport live`. The local build here is
`MAINLINE_BUILD_ID` unset (`'dev'`) and a different transport, so the entry chunk is a
different chunk. `_LARGEST_SERVED_WIRE_BYTES` in `test_static_site.py` is read out of the
**archive** and never out of `console/dist`, exactly as that file instructs, so nothing in
this record moves it and **the 1,087 B deployed headroom figure stands unchanged**.

---

## 7 · What was falsified, and what could not be

A gate that has never refused anything has not been tested.

| assertion | falsified with | result |
|---|---|---|
| **A5** every `public/` file under the wire ceiling | a planted `public/__falsify-oversize.txt`, 204,800 B of `randomBytes` | **REFUSED**, exit 1, both representations named: `204,883 B on the wire, over the 139,264 B ceiling` |
| **A2** no `public/` name in the manifest | a planted `public/index.html` — a name that *is* a manifest key | **REFUSED**, exit 1: `public/index.html appears in dist/.vite/manifest.json` |
| **A6** every `public/` file reaches `dist/` byte-for-byte | the same planted `public/index.html`, overwritten by Vite's emitted shell | **REFUSED**, exit 1: `dist/index.html is not byte-identical to public/index.html` |
| **A6** the copy is a flat tree | a planted `public/assets/` directory | **REFUSED**, exit 1: `public/assets is not a plain file` |
| the 413 path in `test_..._is_under_the_wire_ceiling` | `os.urandom(ceiling + 1)` planted in the served web root, sibling written | **REFUSED**: 413 `response_too_large` on *both* `Accept-Encoding` paths, `vary` set — and the four real files in the same root still answer 200 |
| `/memory.html` is the page and not the SPA fallback | the same web root with `memory.html` removed | `serve` answers **200 `text/html`** — indistinguishable from success by status and media type. Only `x-mainline-static: index.html` tells them apart, which is why that header is asserted |

**A3 and A4 — the byte-identity of the entry closure — could not be falsified from `public/`,
and that is the finding rather than a gap.** Vite copies `publicDir` before Rollup writes the
bundle (§5), and a `public/` file has no path into the module graph at all, so no file placed
there can change an emitted chunk. Producing a violation would require editing `vite.config.ts`,
which R-M2 forbids. The comparator itself is `sha256` and integer equality over two snapshots;
its failure mode is a printed diff of both, and it was exercised on real snapshots ten times.

The last row is worth reading twice. **A missing memory page answers 200 with `text/html`.**
Anyone checking "is `/memory.html` served" by status alone will get a green from an origin
that is serving the console shell instead of the panel.

---

## 8 · `pnpm run ci` — measured, step by step, with the red parts attributed

`pnpm run ci` is `lint && typecheck && test && vite build && check:budgets &&
check:entrypoints && check:licences`. Run individually, 2026-08-15:

| step | result |
|---|---|
| `pnpm run lint` | **RED** — 14 errors, §8.1 |
| `pnpm run typecheck` | **green** |
| `pnpm run test` (vitest) | **RED** — **2,503 tests, 1 failure**, from `--reporter=junit`: `tests/unit/operator/a11y/operator-a11y.test.ts :: a revealed beat is somewhere focus can be sent > every revealed beat can receive programmatic focus`. That file is untracked at HEAD and belongs to the operator-systems plan. **Zero failures in `tests/unit/memory/**`** |
| `vite build` | **green**, 3.8 s |
| `pnpm run check:budgets` | **green** — `evidentiary-shell` 139.6 KB / 220 KB (63 %), `operator-surface` 36.3 KB / 136 KB (27 %), 35 manifest chunks, 102 modules in the entry closure, `memory-register-walk` absent as noted |
| `pnpm run check:entrypoints` | **RED** — one problem, and it is a collision between this plan and the operator plan. §8.2 |
| `pnpm run check:licences` | **green** — every dependency permissive and named |
| `eslint scripts/check-memory-bytes.ts --max-warnings 0` | **green** |
| `ruff check` / `ruff format --check` on `tests/deploy/test_memory_page_is_served.py` | **green** |

`check:budgets` is the number that matters most for R-M2 and it is unchanged in the only way
that counts: §3 shows the closure it measures is byte-identical with and without `public/`, so
whatever it said before this plan, it says now.

### 8.1 · `pnpm run lint` — 14 errors, none in a `w5-bytes` file

| errors | files | owner | new? |
|---:|---|---|---|
| 2 | `public/memory-loop.js`, `public/memory-verify.js` — `Parsing error: "parserOptions.project" has been provided … The file was not found in any of the provided project(s)` | `w3-client`, `w4-recompute` / the memory-visibility lead | **new** with this plan |
| 1 | `scripts/drive-console.mjs` — the same parsing error | pre-existing | **no** — tracked at HEAD `4af05e1`, and HEAD's `eslint.config.js` carries the identical `ignores` list and the identical `parserOptions.project`. `pnpm run lint` was already red before this plan started |
| 1 | `scripts/operator-capture.mjs` — the same parsing error | operator-systems lead | new with that plan |
| 10 | `src/operator/**` — `no-restricted-imports`, a value import of `src/data/types.generated` | operator-systems lead | new with that plan |

**The two `public/*.js` errors are reported to the lead, not fixed here.** The cause is that
`eslint.config.js`'s baseline block sets `parserOptions.project` with no `files` restriction,
so type-aware linting is applied to every `.js` in the tree, and `public/` is in neither
`tsconfig.json` nor `tsconfig.node.json`. The fix is one entry in that file — either
`'public/**'` in the `ignores` array, or a `files: ['public/**/*.js']` block carrying
`...tseslint.configs.disableTypeChecked` — and **`eslint.config.js` belongs to no worker on
this plan**, so `w5-bytes` did not touch it. The alternatives were all worse: an
`eslint.config.js` inside `public/` would be copied to `dist/` and served on the origin, ESLint
9.39 does not cascade flat configs without an unstable flag anyway, and disabling the rule
globally or adding `|| true` is banned.

### 8.2 · `pnpm run check:entrypoints` — R-M2 and the operator plan's new gate collide

```
  • dist/memory.html is on disk but the manifest declares no entry for it. It is a leftover
    from an earlier build with a different input list, and the packer would ship it.
    Rebuild into a clean dist/.
```

**Attributed by measurement, on two clean builds of the same tree:**

| | `check:entrypoints` |
|---|---|
| `public/` moved aside, `vite build`, run | **exit 0** — `2 document(s), 6 asset reference(s), all resolved` |
| `public/` restored, `vite build`, run | **exit 1** — the message above |

`scripts/check-entrypoints.ts` (added by the operator-systems plan; untracked at HEAD, and
`check:entrypoints` was added to `ci` in the same change) lists every `.html` under `dist/` and
requires each one to be a manifest entry with `isEntry`. That is a correct test of *"is this a
leftover from a build with a different input list"* — and it is exactly wrong for a
`publicDir` copy, which is on disk by design and can never be a manifest entry. **The
diagnosis it prints is false: `dist/memory.html` is not stale, and rebuilding into a clean
`dist/` reproduces it every time.**

**Reported, not patched.** `check-entrypoints.ts` belongs to no worker on this plan, and the
memory panel cannot stop landing an HTML file in `dist/` without abandoning R-M2. The fix is
one predicate in that script, and it should not be a name allowlist:

> An HTML file under `dist/` that is **byte-identical to the file at the same relative path
> under `console/public/`** is a `publicDir` copy, not a leftover. Anything else on disk and
> not in the manifest is still the defect this gate was written to catch.

That predicate cannot be fooled by a genuinely stale artefact — if `public/memory.html`
changed, a stale `dist/memory.html` differs and is still refused — and it needs no list of
names to be kept in sync. Whoever owns that script should also decide whether the *asset
reference* walk it performs on `index.html` and `operator.html` should extend to
`memory.html`; R-M2's page references only siblings in the same directory, so it would pass,
and it would then be gating something real rather than tripping over it.

**Until that lands, `pnpm run ci` cannot be green end to end**, and this is one of the two
reasons (the other is §8.1). Neither is fixable from a `w5-bytes` file, and neither is
worked around here: no `continue-on-error`, no `|| true`, no rule disabled, no file of another
worker's edited.

---

### 8.3 · pytest — the 988 lane, before and after

The baseline this worker was given is **988 collected / 987 passed / 0 failed / 0 errors**.
That is not `pytest` with no arguments — which collects **10,800** — it is the demo lane:

```
.venv/Scripts/python.exe -m pytest tests/deploy verticals/mainline/apps/demo-api/tests \
    --crdb=none -q --junitxml=<path>
```

Measured as a **pair**, on the same tree, minutes apart, the only difference being
`--ignore=tests/deploy/test_memory_page_is_served.py`:

| | collected | failed | errors | skipped | passed |
|---|---:|---:|---:|---:|---:|
| **before** — the lane without this worker's file | **988** | **0** | **0** | 247 | 741 |
| **after** — the lane with it | **997** | **0** | **0** | 247 | 750 |
| delta | **+9** | 0 | 0 | **0** | **+9** |

The *collected* count before is **988 on the nose**, which is the baseline's own number, so
the lane this worker was measured against is identified rather than assumed. `+9` is exactly
`tests/deploy/test_memory_page_is_served.py`; nothing else in the lane moved; and the skip
count is **identical**, so **`w5-bytes` added no skip, no `xfail` and no marker**. The 247 are
the cluster-backed cases `--crdb=none` declines to start; with a cluster the baseline run
recorded 987 passed and 1 skip (`test_gate_run.py:1294`, *"jsonschema is not a workspace
dependency"*), and none of the nine new cases needs a database, a network or a scratch schema.

Numbers taken from `--junitxml`, never from a terminal tail.

**The cluster-backed run of the same lane was attempted twice and did not finish**, and that is
recorded rather than dressed up. Both runs reached ~50 % and then hit pytest's own
faulthandler timeout inside a `psycopg` `wait_select`, in
`verticals/mainline/apps/demo-api/tests/test_judge_can_sign.py::judge_walk` →
`conftest.py:387 _apply_chain` — a migration chain blocking on the shared local node while
several workers were writing to it. The node is up and reachable (`localhost:26257` accepts a
socket). **No junitxml was produced, so no cluster-lane number is claimed here.** What the
hermetic pair above already settles is the question this worker owns: the nine cases it added
open no connection, need no schema, and changed the lane by exactly `+9 collected, +9 passed,
0 failed, 0 errors, 0 skipped`.

### 8.4 · The other QA gates

| gate | result |
|---|---|
| `scripts/qa/check_pytest_lanes.py` | **OK** — every declared step agrees with its command line; the self-control refused five planted defects |
| `scripts/qa/skip_ratchet.py` | **OK** — 974 cluster-shaped skips, all attributed, 730 unlanded against a ceiling of 730. `w5-bytes` added none |
| `scripts/qa/ruff_ratchet.py` | **REFUSED**, and **pre-existing**: `unformatted` measured 227 against a baseline of 0, across trees nobody on this plan touched. `ruff format --check packages/trappoint-core` (untouched at HEAD) reports 1 file would be reformatted; `tests/boundary/test_ci_greps.py` likewise; in `tests/deploy` the single unformatted file is `test_furl_compression.py`. `ruff format --check` on `tests/deploy/test_memory_page_is_served.py` says **"1 file already formatted"**, and `ruff check` passes. This looks like a `ruff` version skew against the machine that took the baseline; it is reported, not rebaselined |
| `scripts/qa/check_reuse.py` | **REFUSED**, and pre-existing — §9 |

---

## 9 · `scripts/qa/check_reuse.py` — refused, and it was already refusing

```
REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1265
```

**This is pre-existing at HEAD and no file from this plan can affect it.** Two measurements
say so:

1. The checker enumerates with **`git ls-files -z`** — tracked files only
   (`scripts/qa/check_reuse.py:239`). `git ls-files verticals/mainline/apps/console/public`
   returns **0 files**: everything this plan has written is untracked, so none of it is
   counted.
2. `git grep -l -F 'SPDX-License-Identifier: FSL-1.1-ALv2' HEAD` finds **1,278** files and the
   same grep over the worktree finds **1,278**. The bare-spelling population is byte-identical
   between HEAD and the dirty tree.

The baseline in `qa/reuse-ratchet.json` was taken on 2026-08-10 over **7,120** tracked files;
the tree now holds **7,724**. The ratchet is measuring 604 files' worth of commits made after
the snapshot, and its own `snapshot_caveat` anticipates exactly this: *"Re-take once on the
merge commit with `--write`."*

**`REUSE.toml` was NOT edited, and that is the correct outcome under the brief.** The brief
says to update it *only if the checker fails on the new files*; it does not, and could not.
Editing it would also not help: `non_spdx_spelling` counts a *resolved identifier*, and the
only way a `REUSE.toml` block changes the identifier of a file that carries its own header is
`precedence = "override"` — which would be relicensing 52 files to make a number go down.
That is the move the ratchet exists to refuse.

What was done instead is the thing that keeps the number from rising when these files are
committed: **every file `w5-bytes` wrote uses an SPDX-conformant identifier.**

| file | identifier | why |
|---|---|---|
| `console/scripts/check-memory-bytes.ts` | `LicenseRef-FSL-1.1-ALv2` | the `LicenseRef-` form REUSE 3.3 requires for a licence not on the SPDX list; the bare spelling would push the ratchet up by one |
| `tests/deploy/test_memory_page_is_served.py` | `LicenseRef-FSL-1.1-ALv2` | matches `tests/deploy/test_console_repro.py`, its nearest sibling |
| `docs/demo/memory-visible-BYTES.md` | `CC-BY-4.0` | matches four of the five plans in `docs/demo/`, and it is a documentation licence with a real SPDX identifier |

Existing `REUSE.toml` blocks already cover all three trees, and every one of these files
carries its own header, which `precedence = "closest"` keeps. **No block was added, so the
general-to-specific ordering of that file — where the last matching table wins — is untouched.**

---

## 10 · What was not touched

| | |
|---|---|
| `static_site.DEFAULT_MAX_RESPONSE_BYTES` | `136 * 1024` — unchanged, and **not available to be raised** (R10) |
| `test_static_site.py::_MINIMUM_HEADROOM_BYTES` | `1024` — unchanged, not lowered |
| `verticals/mainline/apps/console/vite.config.ts` | unchanged by `w5-bytes`. It *is* modified in this tree — `git diff --ignore-all-space` is **+35 lines**, the operator plan's `rollupOptions.input` map, where HEAD `4af05e1` declared none and took Vite's default single `index.html`. Still **no `publicDir`** and still no input naming a `public/` file, which is all R-M2 needs, and `test_no_memory_file_can_enter_a_budgets_json_root` asserts the property under either shape |
| `verticals/mainline/apps/console/budgets.json` | unchanged by `w5-bytes` |
| `verticals/mainline/apps/console/package.json` | unchanged — `check-memory-bytes.ts` is a standalone gate, not a `ci` step, because `package.json` belongs to no worker on this plan. **The lead should decide whether to add `"check:memory-bytes": "node scripts/check-memory-bytes.ts"` to the `ci` chain**; it costs two builds (~8 s) |
| `REUSE.toml` | unchanged — §9 |
| `eslint.config.js` | unchanged — §8, reported not fixed |
| AWS, Terraform, SSM, the deployed artefact | untouched. Nothing here deployed, redeployed or read a credential |
| git | nothing committed; the tree is left for the orchestrator |

`pnpm run check:budgets` is not reported as a number in §8 because it is `w5-bytes`'s job to
leave it *unchanged*, and §3 is the stronger statement of the same thing: the closure it
measures is byte-identical with and without this plan's files, so whatever it said before, it
says now.

---

## 11 · The sentence this file exists to make checkable

The memory panel is the axis-1 exhibit and it is served from four static files that the
bundler never touched. **If that ever stops being true, the failure is not a slow page — it is
a 413 on the console's own entry JavaScript, a blank screen for every judge, and an origin
that logs a healthy day while it happens.** `node scripts/check-memory-bytes.ts` is 10 seconds
and it is the difference between believing that and knowing it.
