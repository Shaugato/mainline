<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The lane builds what it tests — the cluster lane's deployment package

**Worker:** W1 of the LANE-HONEST wave (`docs/leads/lane-honest-plan.md`).
**Date:** 2026-08-14. **HEAD:** `eefae1c`, branch `master`.
**Owns:** `.github/workflows/cluster-tests.yml`, `.github/actions/build-demo-package/action.yml`,
and this page.

Every number below was measured on this workstation with the command printed beside it, or
read out of a real GitHub Actions log. Nothing here is estimated.

---

## 1. The defect, decomposed

GitHub Actions run **`31735341117`** (`cluster-tests`, push, HEAD `eefae1c`) reported:

```
cluster lane: 528 collected, 518 executed, 10 skipped, 1 failed, 0 errored
1 failed, 517 passed, 10 skipped in 154.21s (0:02:34)
::error::10 test(s) skipped, ceiling 1
```

The same command on this workstation, where `out/lambda/mainline-demo-api-arm64.zip`
happened to exist, reported **528 collected, 527 executed, 1 skipped**. The nine-test delta
was one `.gitignore`'d build output. From the run's own `short test summary info`:

| source | skips | message |
|---|---|---|
| `test_envelope.py:1016` | 1 | *"no deployment package has been built in this tree"* |
| `test_response_contract.py:893` | 3 | *"the deployed package is not built"* |
| `test_response_contract.py:1144` | 1 | *"the deployed package is not built"* |
| `test_response_contract.py:1210` | 1 | *"the deployed package is not built"* |
| `test_static_site.py:930` | 3 | *"the deployed package … is not built"* |
| `test_gate_run.py:945` | 1 | *"jsonschema is not a workspace dependency"* |
| | **10** | |

**THREE modules, not two.** `test_envelope.py` is the one a reader misses, and a lane that
armed only `test_response_contract.py` and `test_static_site.py` would land at **2** against
a ceiling of **1** — and the next move from there is to raise the ceiling.

**THE CEILING STAYS AT 1.** It lives in `qa/cluster-known-red.json` under
`floor.max_skipped`, it is W3's file, and nothing in this wave's W1 changes moves it. The
tenth skip — `jsonschema` is not a workspace dependency — has nothing to do with the
database or with the package, and it is exactly what a ceiling of one is *for*.

### Why the skips were right, and why the fix is the build

Each of the nine reads the **deployed** tree: the `web/` entries of the finished zip, taken
from the archive's central directory. Each *refuses* to fall back to the packer's INPUT tree
(`console/dist` plus `console/fixtures/bundles/demo-cloud`). That refusal is
`docs/decisions/response-ceiling-authoritative-tree.md`, and it is correct: the input tree
carries eighteen source maps that `build_lambda` strips by default, so a cost assertion
measured there is measured over bytes that never leave the origin.

The skip messages were true sentences. The defect was that no lane in `.github/workflows/`
ever built the artefact, so nine assertions about what this origin costs had **never
executed in CI**, and a skip on a dashboard is the same green tick as a pass.

---

## 2. What landed

### 2.1 `.github/actions/build-demo-package/action.yml`

A composite action, wired into `cluster-tests.yml` between `setup-workspace` and the DSN
step. It runs the recipe `console.yml:86-122` already proves green:

1. `pnpm/action-setup@v4`, reading the version from `console/package.json`'s
   `packageManager` — no `version:` input, so the pin lives in one place;
2. `actions/setup-node@v4`, `node-version: 24`, pnpm store cached on
   `console/pnpm-lock.yaml`;
3. the pin that was requested **is** the pin that arrived (`pnpm --version` against
   `packageManager`);
4. `pnpm install --frozen-lockfile`;
5. `pnpm exec vite build --mode demo`;
6. an interpreter resolution step, then `bash scripts/deploy/build_lambda.sh --arch arm64
   --python <that interpreter>`;
7. the gate.

**`arm64` and not `x86_64`,** because `test_response_contract.py:187` and
`test_static_site.py:825` both name `out/lambda/mainline-demo-api-arm64.zip` literally. A
lane that built only `x86_64` would build a package no assertion opens and would still skip
nine tests.

**`--python` is passed explicitly,** and this is not cosmetic. `build_lambda.sh:169-171`
prefers `$REPO_ROOT/.venv/bin/python` when one exists, `uv sync` puts one there, and a uv
venv carries no `pip` unless it was seeded. Without the explicit interpreter the build dies
forty lines into `pip download` with `No module named pip`, which reads as a broken builder
rather than as a wrong interpreter. The step checks `python -m pip --version` first and
fails with that sentence in the annotation.

**`MAINLINE_BUILD_ID` is deliberately NOT set.** `vite.config.ts:76` inlines it into the
bundle through `define`. Setting it to `${{ github.sha }}` or a run id would change the
content hash of `assets/index-<hash>.js` on **every run**, so the byte counts the demo-api
suite pins — and the whole I3 derivation resting on them — would be unpinnable by
construction. Unset means `'dev'`, which is what a developer's build and a reviewer's build
both use. `MAINLINE_ATTESTATION` is unset for the same reason: the signature path is decided
by a committed file, and a CI override would make the artefact a statement about the
workflow rather than about the repository.

### 2.2 The gate, and why it counts entries rather than stat'ing a file

`_PACKAGE.is_file()` is what the nine tests check before deciding to run. **A build that
produced a zip with an empty `web/` would satisfy `.is_file()`** — and the tests would then
skip anyway, on `if not entries`, while the action reported a successful build. The lane
would have gained a step, kept its ten skips, and looked fixed.

So the gate opens the archive's **central directory** (`zipfile.ZipFile.infolist()`, the
same source `test_response_contract.py:862-879` and `test_static_site.py:923-941` read) and
asserts three things, each of which fails the lane:

| # | assertion | why |
|---|---|---|
| 1 | the zip exists | nine assertions read this path and SKIP when it is absent |
| 2 | at least one `web/` entry | an empty `web/` skips the nine while looking built |
| 3 | **zero** `*.map` entries, anywhere in the archive | `--strip-source-maps` is the default since 2026-08-13; the maps are 18 files / 2,586,994 B of billable egress on a Function URL whose `authorization_type` is `NONE` |

All three were exercised against real inputs before landing:

```
real arm64 zip          -> rc 0, "entries 250 total, 114 under web/", "maps 0"
zip with no web/ entry  -> rc 1, "::error title=the built package carries no web tree::"
zip carrying one .map   -> rc 1, "::error title=the built package ships source maps::"
no zip at all           -> rc 1, "::error title=the deployment package was not built::"
```

The gate also publishes the built package's shape to `$GITHUB_STEP_SUMMARY` — entry counts,
total bytes, largest identity object, largest gzipped sibling, `sha256`. Those are the
inputs to interface I3 and to the cost model, and `docs/leads/lane-honest-plan.md` **R10**
records that `docs/deploy/COST-BOUND.md` is false about them. A reader who needs the real
figures should not have to rebuild the artefact to get them; from now on every run prints
them.

### 2.3 The R6 changes to `cluster-tests.yml`

* **The container log is folded, not quieted and not shortened.** `docker logs … | tail -60`
  now sits inside `::group::` / `::endgroup::`. Measured over run `31735341117`: those 60
  lines are 943–1003 of a 1,023-line log, so a reader who opens a failed run lands on
  CockroachDB's session log with the failing assertion ~180 lines above it. Both obvious
  alternatives were refused in writing: `tail -20` discards the part of an event log
  furthest from the failure and usually the part that explains it, and a container log
  filter would silence exactly the case the step exists for.
* **The JUnit XML and the raw pytest stdout are uploaded** (`actions/upload-artifact@v4`,
  `if: always()`), so `gh run download` yields two files instead of 1,023 interleaved lines.
  `if-no-files-found: warn` is *chosen*, not defaulted: a collection error aborts the job
  before pytest writes a JUnit file, and that already carries its own `::error` — a second
  red for one cause teaches a reader that the lane fails twice for one problem.
* **pytest's stdout is captured with `tee`, not with `>`.** This suite is I/O-bound and
  silent for minutes under a redirect, and healthy runs have been killed for looking hung.
  The capture is `… | tee "${captured}"` followed by the file's existing `rc=$?`, which
  under `set -o pipefail` is pytest's own status whenever `tee` could write, and non-zero
  (fails closed) when `tee` could not. Verified directly, bash 5.2.37:

  ```
  set +e; (exit 7) | tee /dev/null; rc=$?; set -e          ->  rc = 7
  set +e; (echo hi; exit 3) | tee /nonexistent/x; rc=$?    ->  rc = 1   (tee's, non-zero)
  ```

  **`${PIPESTATUS[0]}` was written first and then withdrawn**, and this is the one place
  in this change where a control nearly stopped discriminating without anyone noticing.
  `tests/ci/test_cluster_lane_report.py:1002` reads the literal string `rc=$?` out of
  `cluster-tests.yml` as the wiring on which every one of its `--pytest-rc` controls
  rests. With `PIPESTATUS` in the suite step, that assertion **still passed** — satisfied
  by the *collection* step's unrelated copy of `rc=$?` twenty lines above. A control that
  passes for the wrong reason is worse than the defect it was meant to catch, so the step
  went back to `rc=$?`. (Measured incidentally: a bare `rc=$?` assignment resets
  `PIPESTATUS` to `(0)`, so the two cannot be captured and cross-checked either.)

* **The long rationale moved out of the `run:` body's neighbourhood into comments above
  the step** — plan item R6.4. GitHub echoes a `run:` body into the log and does not echo
  the comment; over run `31735341117` that echo was 186 of 1,023 lines. Nothing was
  deleted. The `# trappoint:pytest-lane=cluster` marker deliberately stayed **inside** the
  step: `scripts/qa/check_pytest_lanes.py` binds a marker to the first pytest invocation
  within `MARKER_REACH = 40` lines below it, and the first draft of this change pushed the
  invocation out of that window. The checker caught it —
  *"`trappoint:pytest-lane=cluster` has no pytest invocation within 40 lines below it"* —
  and the fix was to move the prose, **not** to raise `MARKER_REACH`, which is a measured
  constant (33 lines plus headroom) and whose own file says raising it "is not a
  documentation edit". After the fix: `40 invocations -> 14 declared, 26 undeclared
  (ceiling 26), OK`.

* **`scripts/ci/lane_log_digest.py` is called after the report, in its own step.**

### 2.4 The one deviation from the plan's wording, stated rather than made quietly

`docs/leads/lane-honest-plan.md` §3 and the W1 brief say to call the digest "after the
report". It is called after the report — but as its **own step** with `if: always()`, not as
a further line inside the suite step. The reason:

* digest LAST *inside* the step needs a trailing `exit "${verdict_rc}"`, and that replaces
  the property that step is built on — *"the last command of the step exits with pytest's
  own status when pytest failed, so there is nothing to delete that does not delete the
  run"* — with a single deletable line standing between the verdict and the job's status.
  That is a weakening of an existing control, and the brief forbids weakening controls.
* digest BEFORE the verdict puts a program that *can* fail in front of the one that
  decides, so a broken diagnosis tool would hide the diagnosis.

As its own step after the verdict, it is literally after the report, it cannot come between
pytest's exit status and `--pytest-rc`, and deleting it cannot turn a red run green.
`lane_log_digest.py` exits 0 on every input by construction and emits no `::error`, so the
verdict stays in exactly one place. `always()` rather than `failure()` because the **skip
census is the half a reader needs on a GREEN run** — ten skips against a ceiling of one is
the defect this whole wave was about, and a digest that only appeared on red would never
have published it.

`timeout-minutes` rose **25 → 30**. That is a reliability bound, not a spend bound, and it
rose because the job's work grew by a `pnpm install`, a `vite build` (3.67 s measured), a
`pip download` of two manylinux wheels and a 250-entry pack — about two further minutes on
a cold runner.

---

## 3. THE NINE, MEASURED — and the tenth nobody expected

**They do not all pass.** This section is the recorded outcome the wave's "done" asks for.

### 3.1 How they were measured

The lane has not run yet, so the nine were measured the closest honest way available: by
building the console and the package on this workstation exactly as the action does, and
running the three modules against the result.

```
# 1. the console, twice, into scratch out-dirs
cd verticals/mainline/apps/console
CI=true pnpm install --frozen-lockfile
CI=true pnpm exec vite build --mode demo --outDir dist-repro-w1  --emptyOutDir
CI=true pnpm exec vite build --mode demo --outDir dist-repro-w1b --emptyOutDir
  -> the two builds are BYTE-IDENTICAL across all 49 entries.

# 2. the package, from the fresh dist
bash scripts/deploy/build_lambda.sh --arch arm64
  -> sha256 f52b2165fe327eb6ae76ccf9b63c02af522b8a2e567005b76f3e740578b6e597

# 3. the three modules
.venv/Scripts/python.exe -m pytest \
  verticals/mainline/apps/demo-api/tests/test_envelope.py \
  verticals/mainline/apps/demo-api/tests/test_response_contract.py \
  verticals/mainline/apps/demo-api/tests/test_static_site.py \
  --crdb=none -q -p no:cacheprovider --junitxml=<report>
  -> tests=196 failures=8 errors=0 skipped=0
```

The tree's `console/dist` and `out/lambda/*.zip` were **restored** afterwards, byte-for-byte
(`sha256 cb34e12349…`), and the three modules re-run: `196 passed`. Other workers in this
wave are running the same suite concurrently and must not inherit a build output they did
not ask for.

### 3.2 The outcomes

| # | node id | outcome |
|---|---|---|
| 1 | `test_envelope.py::test_a_built_package_carries_no_banned_distribution_and_no_source_maps` | **PASS** |
| 2 | `test_static_site.py::test_every_sibling_in_the_deployed_package_is_reachable_only_by_negotiation` | **PASS** |
| 3 | `test_static_site.py::test_the_deployed_package_is_the_tree_the_ceiling_was_derived_from` | **FAIL** |
| 4 | `test_static_site.py::test_serving_the_deployed_package_derives_the_ceiling_end_to_end` | **FAIL** |
| 5 | `test_response_contract.py::test_the_largest_file_in_the_built_web_tree_is_the_one_the_ceiling_refuses` | **FAIL** |
| 6 | `test_response_contract.py::test_the_built_web_tree_has_not_outgrown_its_declaration` | **FAIL** |
| 7 | `test_response_contract.py::test_every_identity_object_in_the_deployed_tree_serves_or_is_a_declared_refusal` | **FAIL** |
| 8 | `test_response_contract.py::test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal` | **FAIL** |
| 9 | `test_response_contract.py::test_the_built_web_tree_matches_the_shape_the_flood_arithmetic_assumed` | **FAIL** |
| **+1** | `test_response_contract.py::test_the_ceiling_refuses_something_it_governs` | **FAIL — and this one is not in the nine** |

The tenth is important and was not predicted by anybody's brief. It does **not** skip: it
calls `_deployed_entries()` directly and takes an `if entries:` branch, so with no package
built it runs, skips the tree half, and goes green. It is **passing in CI today** and goes
red the moment the lane builds the artefact. One root cause, ten tests.

### 3.3 The one cause, named

Every one of the eight failures is an exact equality against a constant that was measured
over a package built from a `console/dist` dated **2026-08-10 21:04**. The console source at
HEAD is one commit newer — `b0fe884` (2026-08-11 18:31) touched six console files — so a
fresh `vite build` at HEAD produces a different tree. Sample assertion text, verbatim:

```
the largest object in the web/ entries of …-arm64.zip is now assets/index-BKZMI9SJ.js
at 433564 B, above the declared assets/index-BjAGxrVJ.js at 433396 B.
```

```
assert 1274726 == 1274342     (web tree total bytes)
assert  124173 ==  124127     (largest gzipped sibling)
```

**This is a stale artefact, not build nondeterminism.** Two consecutive fresh builds are
byte-identical across all 49 dist entries, and ~~the console source is clean against HEAD
(`git status --porcelain` names nothing under `apps/console`)~~. The currently-green local run
is green against a `dist/` that no longer corresponds to the committed source — which is
precisely the class of defect this repository exists to make visible, and building in-lane
is what made it visible.

> **RE-MEASURED 2026-08-15. ONE HALF OF THAT PARAGRAPH IS CONFIRMED AND THE OTHER HALF IS
> STRUCK.** Both halves were checked by `scripts/deploy/console_repro.py`, which builds N≥3
> times and records the name, byte size and sha256 of **every** emitted asset into
> `evidence/deploy/console-repro.json`. R5 of this page permits a derived number to be
> re-recorded when the build that produced it is named, and both builds are named below.
>
> * **CONFIRMED, and stronger than it was written.** *"Byte-identical"* holds at **N = 3**, not
>   2, and in **three** independent configurations: `runs["committed-phase1"]`,
>   `runs["committed-phase2"]` and `runs["worktree-phase2"]` each record one tree digest across
>   three builds, `byte_identical: true`, `assets_that_differ: []`. **The console build is
>   reproducible.** Nothing in this page rests on nondeterminism and nothing needs to.
> * ~~**FALSE as a matter of bytes, and true only as git reported it.**~~ **CORRECTED: the
>   console source was NOT clean against HEAD when §4's figures were taken.** Git for Windows
>   ships `core.autocrlf=true` at system scope; a file checked out under it holds CRLF in the
>   worktree and LF in the index, and the index's cached stat size is the CRLF size, so
>   `git status` declares the entry unmodified **without re-reading it**. W1 counted
>   **fifty-one** files under `apps/console` drifted that way at the time. `git status
>   --porcelain` really did name nothing — and the bytes `vite` read were not the committed
>   bytes. *(The drift has since been repaired where it reached the bundle:
>   `evidence/deploy/console-repro.json` → `runs[*].source.eol` reports **31** worktree-CRLF
>   files today and **none of them under `src/`**. `tests/deploy/test_console_repro.py` now
>   fails by name on any `src/**` file whose worktree bytes differ from the commit only in
>   line endings, so the state that produced `index-BKZMI9SJ.js` is an assertion away rather
>   than a discovery away. A worktree build can still differ from the committed one — today's
>   does, because the seventeenth resource is genuinely uncommitted — but it can no longer
>   differ **invisibly**.)*
>
> **That is what produced `index-BKZMI9SJ.js`.** Reproduced deliberately by W1 of the
> package-and-verify wave: export HEAD, convert `src/design/primitives/instrument.module.css`
> from LF to CRLF, change nothing else, build.
>
> ```
> committed (LF)          assets/index-DzVoV1YM.js  433,564 B   identity total 794,736 B
> one CSS module CRLF     assets/index-BKZMI9SJ.js  433,564 B   identity total 794,741 B
> all 51 drifted CRLF     assets/index-BKZMI9SJ.js  433,564 B   identity total 794,741 B
> ```
>
> A CSS-module scoped class name is a hash of the module's bytes, and a hash is a
> **fixed-length** string — so its value moves and the bundle's length does not, which is
> exactly how two different files come to be recorded at one identical byte count. Of the 51
> drifted files, **one** reaches the emitted identity bytes; the other fifty move only source
> maps, which the packer strips.
>
> **So the sentence that has to change is the diagnosis, not the number.** §3.2's eight
> failures were still a stale artefact rather than nondeterminism — that part stands. What was
> wrong was believing the *replacement* was clean: the fresh build this page recorded was
> itself taken over a drifted worktree, and the build the committed source produces is
> `assets/index-DzVoV1YM.js`, which is the file the Function URL serves and the file
> `out/lambda/mainline-demo-api-arm64.zip` carried when this was written on 2026-08-15.
> *(**Later the same day** the zip under that path was rebuilt from the worktree console with
> `--console-transport live` and now carries `assets/index-DJX27H0M.js` — §4's second
> annotation. The origin is unchanged and still answers with `assets/index-DzVoV1YM.js`; what
> moved is the package on disk, which is why the sentence above names both separately.)*
> **Restore
> drifted bytes rather than re-recording a hash measured while they were there** —
> `tests/deploy/test_console_repro.py` now fails by name on any `src/**` file whose worktree
> bytes differ from the commit **only** in line endings, and a genuine edit is not drift and
> does not fail it. The full derivation is `docs/deploy/console-build.md` §1.

### 3.4 The build reproduces on Linux — measured, not assumed

The obvious objection to every number in §4 is that they were taken on a Windows
workstation while the lane runs on `ubuntu-24.04`, and `rollup`/`esbuild` ship
platform-specific native binaries. That objection was **tested rather than argued around**,
in both halves of the pipeline.

*The console build.* A clean copy of `apps/console` (no `node_modules`, no `dist`) was built
inside a Linux container from the committed lockfile:

```
docker run --rm -v <clean console copy>:/console -w /console -e CI=true node:24 bash -c \
  'corepack enable && corepack prepare pnpm@11.5.3 --activate &&
   pnpm install --frozen-lockfile &&
   pnpm exec vite build --mode demo --outDir dist-linux-w1 --emptyOutDir'
```

Node **v24.19.0** in the container against **v24.14.0** on the workstation, pnpm 11.5.3 on
both. Every emitted asset matched by **name and by byte count** — and a Vite asset name *is*
a content hash, so matching names are matching bytes:

```
433564  assets/index-BKZMI9SJ.js        51266  assets/surface-AicCA6US.js
 28445  assets/surface-hCYfrFDi.js       28188  assets/surface-BkUjugiq.js
 18084  assets/index-C498vmEA.css         6258  .vite/manifest.json
                     … all 31 non-map entries identical …
```

*The `.gz` siblings.* The packer writes them with `zlib.compressobj(9, DEFLATED,
-MAX_WBITS)` and a hand-written gzip container, so the only platform-sensitive part is
zlib's deflate. The two largest assets were compressed by both interpreters:

```
Windows  CPython 3.13.14  zlib 1.3.1   gz9=124173  sha256(gz)=a0fbf12fd1382596  index-BKZMI9SJ.js
Linux    CPython 3.13.15  zlib 1.3.1   gz9=124173  sha256(gz)=a0fbf12fd1382596  index-BKZMI9SJ.js
Windows  …                             gz9= 13673  sha256(gz)=000af64845b54542  surface-AicCA6US.js
Linux    …                             gz9= 13673  sha256(gz)=000af64845b54542  surface-AicCA6US.js
```

Byte-identical, digest included. **So §4's figures are not a workstation artefact**, and the
residual is one version step: `actions/setup-python`'s CPython on `ubuntu-24.04` links the
system zlib, which is 1.3 there rather than 1.3.1. Deflate output is unchanged between those
two point releases as far as this worker can establish, but it was not measured, and the
lane's own first run is the measurement that settles it.

> **STILL TRUE, AND ABOUT A DIFFERENT TREE THAN IT MEANT TO BE — annotated 2026-08-15.** The
> cross-platform claim this section makes is unaffected by §3.3's correction and is not
> withdrawn: two interpreters on two operating systems emitted the same asset names, the same
> byte counts and the same `.gz` digests, and that is a real result about `rollup`, `esbuild`
> and `zlib`. **What moved is which source tree both halves were built from.** The Linux
> container was handed *"a clean copy of `apps/console`"* copied out of the **worktree**, so it
> carried the same CRLF drift the Windows build did — which is why both agree on
> `index-BKZMI9SJ.js` and on `gz9 = 124,173`. Agreement across platforms over one input is
> exactly what this section set out to show and exactly what it showed; it is not evidence
> about the committed input, and it was read as though it were.
>
> **The committed input's figures, for the same two quantities**
> (`evidence/deploy/console-repro.json` → `runs["committed-phase1"]`, three builds, byte
> identical, `git archive`'d from HEAD so no worktree can reach it):
>
> ```
> committed HEAD, LF      assets/index-DzVoV1YM.js  433,564 B identity   124,177 B gzip(9)
> drifted worktree, CRLF  assets/index-BKZMI9SJ.js  433,564 B identity   124,173 B gzip(9)
> ```
>
> Same length, four bytes apart on the wire, different files. ~~**`124,177 B` is the figure the
> response ceiling is derived from today**, it is the one the deployed package carries, and it
> is what `verticals/mainline/apps/demo-api/tests/test_static_site.py` declares as
> `_LARGEST_SERVED_WIRE_BYTES`.~~ **CORRECTED 2026-08-15: `124,177 B` is the figure the ceiling
> was CHOSEN from, over the 2026-08-14 tree, and it is the figure the package the Function URL
> is answering with carries.** It is no longer what the package on disk measures — see §4's
> second annotation, where the package of record reads **129,400 B** — and under ruling
> **R10** (`docs/leads/reconcile-constants-plan.md` §1) the ceiling is not re-derived from
> either: it stands at **139,264 B**, kept by interface I3. The `124,173` above is kept because
> it is the measurement that
> was taken, and because the four-byte gap between two builds of the *same commit* is the whole
> of §3.3's correction stated as a number.

---

## 4. THE FRESH BUILD'S REAL NUMBERS

Recorded here because `docs/leads/lane-honest-plan.md` **R10** names
`docs/deploy/COST-BOUND.md` I4/I6 and `docs/leads/cost-bound-plan.md:25,28` as false about
this repository and assigns them to the cost lead. **W1 reports; W1 does not edit those
pages.**

Built 2026-08-14 on this workstation, `bash scripts/deploy/build_lambda.sh --arch arm64`,
from a `vite build --mode demo` of clean HEAD `eefae1c`.

| quantity | the tree's stale package | **the fresh build at HEAD** | Δ |
|---|---|---|---|
| zip `sha256` | `cb34e12349cb…` | `f52b2165fe32…` | — |
| zip bytes | 7,701,872 | **7,702,078** | +206 |
| entries in the zip | 250 | **250** | 0 |
| `web/` before the strip | 75 entries, 3,571,990 B | **75 entries, 3,572,305 B** | +315 |
| source maps removed | 18 files, 2,586,960 B | **18 files, 2,586,994 B** | +34 |
| `web/` after the strip | 57 entries, 985,030 B | **57 entries, 985,311 B** | +281 |
| `.gz` siblings written | 57 files, 289,312 B | **57 files, 289,415 B** | +103 |
| `web/` as packed | 114 entries, 1,274,342 B | **114 entries, 1,274,726 B** | +384 |
| largest identity object | `assets/index-BjAGxrVJ.js`, 433,396 B | **`assets/index-BKZMI9SJ.js`, 433,564 B** | +168 |
| largest gzipped sibling | `…BjAGxrVJ.js.gz`, 124,127 B | **`…BKZMI9SJ.js.gz`, 124,173 B** | +46 |
| 2nd largest identity | `assets/surface-Csi7pmRe.js`, 51,266 B | **`assets/surface-AicCA6US.js`, 51,266 B** | 0 |
| unzipped | — | **26,270,873 B** | — |

`docs/deploy/COST-BOUND.md` declares **I4 = 1,554,168 B** and **I6 = 3,571,990 B over 75
files** while its own summary correctly gives 124,127 B and states the package holds **0**
source maps. For the record, against the fresh build: 1,554,191 B is
`assets/index-BKZMI9SJ.js.map`, a **source map**, and the package holds **zero** of them —
it is not an object this origin can emit at all. 3,572,305 B / 75 files is the packer's
INPUT tree *before* the strip, not the served tree; the served tree is **1,274,726 B over
114 entries**, of which what actually goes on the wire for the biggest single response is
**124,173 B**.

> **§4 ANNOTATED 2026-08-15 — THE "FRESH BUILD AT HEAD" WAS NOT A BUILD OF HEAD.**
>
> **Every figure in the table above stays.** They were measured, they are reproducible from the
> input that produced them, and R5 of this page permits a derived number to be re-recorded
> *"naming the build"* — so the answer is to name the build, not to delete the row.
>
> **The build named in the sentence above the table — *"from a `vite build --mode demo` of
> clean HEAD `eefae1c`"* — is not the build that produced these numbers.** §3.3's annotation
> has the mechanism: the worktree carried CRLF line-ending drift in fifty-one files under
> `apps/console`, `git status --porcelain` could not see it, and one of the fifty-one
> (`src/design/primitives/instrument.module.css`) reaches the emitted identity bytes. So the
> right-hand column is **a build of HEAD-plus-drift**, and `index-BKZMI9SJ.js` is its name.
>
> **What clean HEAD emits, and what is on the origin.** Read out of
> `out/lambda/mainline-demo-api-arm64.zip` with `zipfile` over its `web/` entries, **earlier on
> 2026-08-15**, when that path held `sha256 12fcba7a…` — the package the plan's
> `source_code_hash` names and the one the Function URL is answering with:
>
> | quantity | §4's right column — HEAD **+ CRLF drift** | **the committed source** — measured from the zip | Δ |
> |---|---|---|---|
> | `web/` as packed | 114 entries, 1,274,726 B | **114 entries, 1,274,743 B** | +17 |
> | `web/` identity after the strip | 57 entries, 985,311 B | **57 entries, 985,306 B** | −5 |
> | `.gz` siblings written | 57 files, 289,415 B | **57 files, 289,437 B** | +22 |
> | source maps in the package | 0 | **0** | — |
> | largest identity object | `assets/index-BKZMI9SJ.js`, 433,564 B | **`assets/index-DzVoV1YM.js`, 433,564 B** | 0 B, different file |
> | largest gzipped sibling | `…BKZMI9SJ.js.gz`, 124,173 B | **`…DzVoV1YM.js.gz`, 124,177 B** | +4 |
> | `web/index.html` | — | **4,655 B** | — |
> | zip bytes / entries | 7,702,078 / 250 | **7,703,067 / 250** | +989 / 0 |
>
> **The identity row is the one to read twice: same 433,564 B, different file.** A CSS-module
> class name is a fixed-length hash, so drift moves the content and not the length — which is
> how this repository came to hold two records at one byte count and spend a wave deciding
> which was wrong. Neither was arithmetic; one was a build nobody could re-measure.
>
> **Reproducibility is not in question and was measured rather than argued.**
> `evidence/deploy/console-repro.json` records three configurations × three builds, every one
> `byte_identical: true` with `assets_that_differ: []`, and the committed-source entry chunk's
> `sha256 4596d00cb33ee2d1…` is byte for byte the `web/assets/index-DzVoV1YM.js` inside the zip
> above. **The build reproduces; the input was not what the sentence said it was.**
>
> **What this does NOT change.** The ceiling below — `136 × 1024 = 139,264` — is unmoved and
> re-derives from the committed figure as readily as from the drifted one:
> `1.10 × 124,177 = 136,594.7`, next 8 KiB boundary `17 × 8192 = 139,264`, and
> `0 < 124,177 < 139,264 < 433,564` holds with **exactly one** identity object refused. The
> conclusion of the next subsection is correct under both builds and is not restated to fit.
> *(Both builds in that sentence are 2026-08-14-generation consoles. A third build has since
> been packaged and the derivation no longer lands on 139,264 over it — the annotation
> immediately below carries it, and the ceiling still does not move.)*

> **§4 ANNOTATED A SECOND TIME, 2026-08-15 — A THIRD CONSOLE IS NOW PACKAGED, AND THE CEILING
> STILL DOES NOT MOVE.** Every figure above stays. This annotation adds a dated column and
> nothing else.
>
> **The artefact, named by digest rather than by path**, because one path has now held three
> different packages in two days: `out/lambda/mainline-demo-api-arm64.zip`,
> `sha256 7e49fd5e1426a4d2aaba12a2cd7aa086c95430f0b5daa3645bc8b55eaaed2738`, built
> `--console-transport live` with `MAINLINE_BUILD_ID=3933b97`, read out of its own central
> directory on 2026-08-15. **It has not been applied and nothing was redeployed to measure it**
> — the Function URL is still answering with `sha256 12fcba7a…` and its
> `assets/index-DzVoV1YM.js`.
>
> | quantity | **the committed source** (`12fcba7a…`), the column above | **the package of record** (`7e49fd5e…`), read 2026-08-15 | Δ |
> |---|---|---|---|
> | `web/` as packed | 114 entries, 1,274,743 B | **114 entries, 1,308,543 B** | +33,800 |
> | `web/` identity after the strip | 57 entries, 985,306 B | **57 entries, 1,012,812 B** | +27,506 |
> | `.gz` siblings written | 57 files, 289,437 B | **57 files, 295,731 B** | +6,294 |
> | source maps in the package | 0 | **0** | — |
> | largest identity object | `assets/index-DzVoV1YM.js`, 433,564 B | **`assets/index-DJX27H0M.js`, 457,123 B** | +23,559 |
> | largest gzipped sibling | `…DzVoV1YM.js.gz`, 124,177 B | **`…DJX27H0M.js.gz`, 129,400 B** | +5,223 |
> | 2nd largest identity | `assets/surface-BcxWkbKu.js`, 51,266 B | **`assets/surface-COD-Iou0.js`, 51,266 B** | 0 B, different file |
> | `web/index.html` | 4,655 B | **4,655 B** | 0 |
> | identity objects over the 139,264 B ceiling | 1 | **1** | 0 |
>
> **The growth is not drift and is not a defect.** It is a seventeenth declared console resource
> and a 23,138 B `gate-run.schema.json` imported as raw text on the critical path — a decision
> `docs/deploy/console-build.md` §2 records. **The identity length moved this time**, which is
> what distinguishes it from §3.3's CSS-module story, where the length was fixed and only the
> hash moved.
>
> **What the ceiling does about it, under ruling R10** (`docs/leads/reconcile-constants-plan.md`
> §1): nothing, and that is the ruling rather than an omission.
> `DEFAULT_MAX_RESPONSE_BYTES` stands at `136 * 1024 = 139,264`, **not raised and not lowered**,
> and what is asserted against the tree is the straddle, interface I3 and exactly-one-refusal:
>
> ```
> straddle   0 < 129,400 < 139,264 < 457,123                          HOLDS
> I3         129,400 ≤ 139,264 < 1.20 × 129,400 = 155,280             HOLDS
> refusals   identity objects over 139,264 : 1 of 57                  HOLDS
>            today that object is assets/index-DJX27H0M.js, 457,123 B
> headroom   139,264 − 129,400 = 9,864 gzipped bytes   (it was 15,087)
> ratio      139,264 / 129,400 = 1.076                 (it was 1.121)
> ```
>
> **The derivation is provenance now, not law.** `139,264` was CHOSEN over the 2026-08-14 tree
> (`floor(1.10 × 124,177) = 136,594 → 17 × 8,192 = 139,264`); over the package of record the
> same arithmetic emits `floor(1.10 × 129,400) = 142,340 → 18 × 8,192 = 147,456`. **147,456 is
> recorded and refused**: a cost bound is not raised so a formula agrees. The ratio falling
> **1.121 → 1.076** is the *safe* direction — the `1.20` ratchet guards against the ratio
> climbing, where a ceiling refuses nothing at all — and **9,864 gzipped bytes** is now the
> number to watch, because a console growth past it puts the origin's own entry chunk over its
> own ceiling.

### The ceiling does not move, and it did not need to

`136 * 1024 = 139,264` is authoritative and stays. Re-derived from the fresh measurement
with `test_static_site._derive_ceiling`'s own arithmetic:

```
1.10 × 124,173 = 136,590.3  ->  next 8 KiB boundary = 17 × 8192 = 139,264
139,264 / 124,173 = 1.12153  ->  round(_, 3) = 1.122
I3:  124,173 ≤ 139,264 < 1.20 × 124,173 = 149,007.6      SATISFIED
```

Both declaration-only tests survive the fresh numbers unchanged: `derived == 139_264` still
holds, and `round(ratio, 3) == 1.122` still holds. **Nothing in the fresh tree exceeds the
ceiling, and no cost regression was found.** The largest object this origin can put on the
wire grew by 46 bytes — 0.037 %.

> **THE HEADING IS STILL TRUE AND THE MIDDLE LINE OF THAT BLOCK IS NOW HISTORY — annotated
> 2026-08-15.** The ceiling has not moved: it is `136 * 1024 = 139,264` and this wave did not
> open the file it lives in. What has moved is the *status* of the arithmetic printed above.
> Over the package of record (`sha256 7e49fd5e…`, §4's second annotation) the same derivation
> emits `18 × 8,192 = 147,456`, the I3 ratio is **1.076** rather than 1.122, and the I3 bound
> reads `129,400 ≤ 139,264 < 155,280`. **Ruling R10** settles which of those is the law: the
> derivation is a **dated record of how 139,264 was CHOSEN**, over the tree it was chosen from,
> and the live assertions are the straddle, I3 and exactly-one-refusal — all three measured
> true. The three lines above are therefore correct **about the build named beside them**, and
> the block is kept, dated, rather than re-run against a tree it was not taken over.

---

## 5. WHY W1 DID NOT RE-RECORD THE CONSTANTS

Ruling **R5** permits it: *"the recorded byte count is the derived side … and may be
re-recorded, naming the build that produced it."* Every one of R5's conditions is met — the
failures are a fresh `vite build` producing different sizes; 139,264 does not move; nothing
exceeds the ceiling. The edit would be five constants and one tuple in
`test_response_contract.py` and four in `test_static_site.py`.

**It was still not made. Three reasons, and the first one that a reader will guess is not
among them.**

The obvious objection — *these are Windows numbers and the lane is Linux* — has been
**measured away**, see §3.4: `node:24` on Linux emits byte-identical assets, and Windows
and Linux CPython 3.13 produce byte-identical level-9 `.gz` siblings, digests included. So
"W1 cannot reproduce this" is not the reason. The reasons are:

1. **The residual is small but it is on the one number the ceiling is derived from.**
   `actions/setup-python`'s CPython on `ubuntu-24.04` links the system zlib — 1.3 there
   against 1.3.1 in both measurements above. Deflate output is believed unchanged across
   that point release; it was not measured, and `_LARGEST_SERVED_WIRE_BYTES` is precisely
   the input to I3. Recording a number that has not been produced by the machine that will
   check it is the same error, in miniature, that §3.4 exists to have avoided.
2. **The move is a cost DECISION, not a transcription.** The assertion's own message says
   so: *"Re-measure, decide the new number is acceptable at concurrency 10 for 30 days,
   then update `_LARGEST_WEB_OBJECT_BYTES`."* `docs/leads/lane-honest-plan.md` **R10**
   assigns the cost documents to the cost lead and directs W1 to **report** the figures
   rather than edit them. The constants in these two test files *are* the cost
   declaration; the same rule points the same way.
3. **The tree is going to move again inside this wave.** `web/bundle/` is the committed
   EvidenceBundle, and `_WEB_TREE_BYTES` / `_IDENTITY_BYTES` count it. A recapture, or the
   demo-seed lead's work on `demo_world.sql` feeding a new capture, moves those totals
   again. A constant re-recorded twice in one wave teaches its next reader that it is
   bookkeeping rather than a bound.

Neither test file is owned by any of the six workers `docs/leads/lane-honest-plan.md` §3
enumerates, which also means nobody in this wave has been asked to review such an edit.

So the honest sequence is:

1. **this change lands**, the lane builds the package, and the nine plus the tenth run for
   the first time;
2. the action's step summary and the uploaded JUnit publish the **runner's** figures —
   `largest identity`, `largest gzipped sibling`, `web bytes`, entry counts, `sha256`;
3. whoever re-records the constants does it **from those figures**, in one commit, naming
   the run id and the artefact `sha256` beside each number, exactly as
   `test_the_built_web_tree_has_not_outgrown_its_declaration`'s own message instructs:
   *"Re-measure, decide the new number is acceptable at concurrency 10 for 30 days, then
   update `_LARGEST_WEB_OBJECT_BYTES` in this file. Do not delete this assertion."*
4. if the runner's `largest gzipped sibling` lands outside `(119,157 … 126,603)` B, the
   derivation moves the ceiling and **that is a decision, not a re-record** — the answer to
   an object above 139,264 B is a smaller artefact, never a bigger ceiling.

> **STEP 4'S WINDOW IS SUPERSEDED AS A LIVE TRIPWIRE — 2026-08-15, ruling R10**
> (`docs/leads/reconcile-constants-plan.md` §1). Its *conclusion* is upheld and is now settled
> law: **a ceiling is never raised to admit a bigger artefact**, and 147,456 B was recorded and
> refused when the arithmetic offered it (§4's second annotation). What is retired is the
> **window** as a rule anything must satisfy. `ceil(floor(1.10·g)/8192)·8192` has a rounding
> step, so it returns 139,264 for **every** `g` in `[119,158, 126,604]` — the band is a
> 7,447-byte *bundle-size budget*, not a statement that the ceiling is correct, and this
> repository already owns a bundle budget
> (`verticals/mainline/apps/console/scripts/check-budgets.ts`).
>
> **The tripwire that replaces it, and it has teeth:** `139,264 − g` is the gzipped headroom,
> and it is **9,864 B** measured on the package of record. A console growth larger than that
> puts `g` above the ceiling and the origin answers **413** to its own entry chunk. The
> assertion that catches it is `_assert_i3`'s lower half, not the derivation.

Those constants belong to no worker in this wave (`docs/leads/lane-honest-plan.md` §3
enumerates six owners and neither test file is among them), so this page is where the work
is written down rather than left implied.

**The lane will therefore be RED on its first run,** on nine failing assertions and one that
was passing vacuously — all with a single named cause, all printed in the step summary by
`lane_log_digest.py`, and all about a real staleness that was invisible the day before. That
is the outcome ruling R5 anticipated and the outcome §4.1 of the plan accepts: *"the nine
package-dependent assertions have an outcome recorded — pass or fail, named."*

---

## 6. Full-suite `--crdb=reuse`, BEFORE and AFTER — and why they are not comparable

Taken from `--junitxml`, reading the `<testsuite>` attributes, never a terminal scroll.

| | plan §1.1, clean HEAD `eefae1c` | W1 BEFORE, 11:16 | W1 AFTER, 11:47 |
|---|---|---|---|
| `tests` | 528 | **557** | **570** |
| `failures` | 1 | **20** | **13** |
| `errors` | 0 | **13** | **46** |
| `skipped` | 1 | **0** | **11** |
| executed | 527 | **557** | **559** |
| `time` | 170.5 s | 34.6 s | 738.8 s |

**The BEFORE this worker could take is already not the plan's BEFORE, and the AFTER is not
comparable to either.** The working tree is being changed by other waves while this one
runs. At 11:16 it already carried uncommitted `defeaters.py`, `retry.py`, a modified
`gate_run.py` and `transitions.py`; by 11:47 a new module `test_judge_can_sign.py` had
appeared with 13 further tests. 45 node ids changed status between the two runs and none of
the changes is reachable from anything W1 touched — the dominant one is
`mainline_demo_api.defeaters.DefeaterVocabularyAbsent: mainline.defeater_option holds no
row …`, which is blocker #1 and **R10**'s, owned by the demo-seed lead.

**What W1 changed cannot move any of those numbers, and this is checkable rather than
asserted.** The three files are two YAML documents under `.github/` and one Markdown page.
No Python was added, deleted or edited; nothing under
`verticals/mainline/apps/demo-api/` was touched. The controlled measurement that *is*
meaningful is the one over the modules this work can reach:

```
the three package-dependent modules, --crdb=none, at the restored tree
  BEFORE  196 passed
  AFTER   196 passed
```

and against a fresh in-lane-style build of the same three modules, `8 failed, 188 passed` —
which is §3.2, the outcome this task was asked to record.

Repository controls that read `cluster-tests.yml` were re-run after the change:

```
tests/ci + tests/release          313 passed, 15 skipped, 2 failed
  the two failures are NOT this change:
    test_check_reuse.py::test_the_checker_passes_the_tree_as_committed
        -> UNCOVERED: collected.txt, a file tracked at HEAD eefae1c. `.github` reports
           22 files / 22 with a header / 0 uncovered, so both new files are covered.
    test_ruff_ratchet.py::test_the_ratchet_passes_on_the_real_tree
        -> 683 ruff findings across the tree, in .py files this change does not contain.
scripts/qa/check_pytest_lanes.py  OK  (40 invocations, 14 declared, 26 undeclared, ceiling 26)
tests/ci/test_cluster_lane_report.py  116 passed
```

---

## 7. What is NOT claimed here

* That the lane is green. It is not, and §3.2 says which tests and why.
* That the runner's build equals this workstation's. That is unmeasured, it is the reason
  §5 exists, and the lane's first run is the measurement.
* Anything about `test_gate_run.py:945` (*"jsonschema is not a workspace dependency"*). It
  is the tenth skip, it has nothing to do with the database or with this package, and it is
  what the ceiling of **1** exists for. It stays.
* Anything about `mainline.defeater_option` holding zero rows (**R10**, the demo-seed
  lead's) or about `qa/cluster-known-red.json` (W3's). Neither was touched.

### One thing found in passing, for whoever owns `.gitignore`

`collected.txt` — the output of this lane's own collection step — is **tracked at HEAD
`eefae1c`** and is the single file failing `scripts/qa/check_reuse.py`, against two ratchets
whose baseline is a hard-gated **0**. `.gitignore` names neither it nor the two files this
change adds beside it, `junit-cluster.xml` and `pytest-cluster.txt`. Left as it is, the next
person who runs the lane locally and commits with `-A` repeats the same mistake with two
more files. `.gitignore` is not W1's to edit in this wave, so it is reported here rather
than fixed.

---

## 8. IT LANDED — the run, and every prediction in §§5–7 checked against it

**Worker:** D3, DOCS-TRUE wave, 2026-08-14. **Run:**
[31770005759](https://github.com/Shaugato/mainline/actions/runs/31770005759) — `cluster-tests`,
push, HEAD **`7535670`**, the public tip. Read from the job log, job `94673769475`.

§§1–7 were written before this change had a run id. **They are not edited.** This section
checks each prediction against the run, in the order they were made, and it is written to be
read *beside* them rather than instead of them: a page that quietly re-typed its predictions
after the outcome would be worth nothing.

### 8.1 THE SKIP CEILING — the cure was the build, and the ceiling never moved

The lane's own verdict line, quoted:

```
cluster lane: 570 collected, 569 executed, 1 skipped, 8 failed, 0 errored
8 failed, 561 passed, 1 skipped in 224.11s (0:03:44)
```

| | run 31735341117, `eefae1c` | run 31770005759, `7535670` |
|---|---:|---:|
| collected | 528 | **570** |
| executed | 518 | **569** |
| **skipped** | **10** | **1** |
| `floor.max_skipped` in `qa/cluster-known-red.json` | **1** | **1 — UNCHANGED** |
| lane's verdict on the skip count | **errored: `10 test(s) skipped, ceiling 1`** | **satisfied, exactly** |

**Ten skips became one because the lane started building what it tests. The ceiling was never
touched.** It reads `1` in `git show eefae1c:qa/cluster-known-red.json` and `1` in
`git show 7535670:qa/cluster-known-red.json`. The surviving skip is `test_gate_run.py`'s
*"jsonschema is not a workspace dependency"* — §7 named it in advance as the one the ceiling of
1 exists for, and it is the one that survived.

**This is the sentence that must not be paraphrased into its opposite by any later reader:**

> **The cure for ten skips against a ceiling of one was to BUILD THE PACKAGE IN THE LANE. It
> was never to raise the ceiling, and no document in this repository may present raising it as
> an option that was weighed.** The lane's own comment settles it in the tree:
> *"THIS STEP DOES NOT WEAKEN THE SKIP CEILING; IT REMOVES THE REASON FOR THE SKIPS."*
> (`.github/workflows/cluster-tests.yml:275`)

A ceiling raised to admit ten skips would have converted *"nine assertions did not run"* into
*"nine assertions are fine"*, and on a dashboard those are the same colour. **The lane was
right to error.** The repair paid for itself in a single run: eight defects that had never
been visible in CI became visible in CI, which is §8.2.

### 8.2 THE NINE — §5's prediction was "RED on its first run", and it was right

§5 closed with: *"The lane will therefore be RED on its first run, on nine failing assertions
and one that was passing vacuously — all with a single named cause."*

**Measured: eight failing assertions, one named cause.** The eight, by node id:

```
test_response_contract.py::test_every_identity_object_in_the_deployed_tree_serves_or_is_a_declared_refusal
test_response_contract.py::test_the_built_web_tree_has_not_outgrown_its_declaration
test_response_contract.py::test_the_built_web_tree_matches_the_shape_the_flood_arithmetic_assumed
test_response_contract.py::test_the_ceiling_refuses_something_it_governs
test_response_contract.py::test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal
test_response_contract.py::test_the_largest_file_in_the_built_web_tree_is_the_one_the_ceiling_refuses
test_static_site.py::test_serving_the_deployed_package_derives_the_ceiling_end_to_end
test_static_site.py::test_the_deployed_package_is_the_tree_the_ceiling_was_derived_from
```

**Eight and not nine, and the difference is not a rounding.** §3.2 counted nine
package-dependent assertions plus one passing vacuously; at `7535670` the suite has grown from
528 to 570 collected and the set is not the same set. The number to trust is the one the
runner printed, and it is 8. **A prediction that is nearly right is reported as nearly right.**

The single cause, from the runner:

```
AssertionError: the deployed package refuses ['assets/index-DzVoV1YM.js [identity]'] …
    - 'assets/index-BjAGxrVJ.js [identity]': 413      ← declared in the test
    + 'assets/index-DzVoV1YM.js [identity]': 413      ← built by the lane
AssertionError: assets/index-DzVoV1YM.js is 433564 B … at or above the 139264 B ceiling
AssertionError: the largest object … is now assets/index-DzVoV1YM.js at 433564 B, above the
   declared assets/index-BjAGxrVJ.js at 433396 B.
AssertionError: assert 124177 == 124127     ← _LARGEST_SERVED_WIRE_BYTES
```

**Read what did NOT move: `139264`.** That is `136 * 1024`, it is identical in the test and in
the run, and the ceiling is not the thing that broke. What broke is that the content-hashed
**filename** and the **byte counts** recorded in the two test files describe a different build
of the console than the runner produced — 433,564 B against a declared 433,396 B, and a
largest gzipped sibling of **124,177** B against a declared **124,127** B.

### 8.3 §5's four-step sequence, checked — and step 4's boundary, which held

§5 wrote the honest sequence as four numbered steps. Steps 1 and 2 are now done:

1. ✅ **the change landed** and the lane built the package — the failures reference
   `/home/runner/work/mainline/mainline/out/lambda/mainline-demo-api-arm64.zip`, so the zip
   existed on the runner;
2. ✅ **the runner's figures are published** — in the step summary via `lane_log_digest.py`,
   and in the uploaded artifact `cluster-lane-31770005759-1` (JUnit XML plus raw pytest
   stdout, `sha256 8a49ff2f8141210464264f36b08ea3221c86a101717055c5807a1c424fc81df4`,
   25,282 B, artifact id `9207831953`);
3. ⏳ **the re-record is owed**, from *those* figures, in one commit naming the run id;
4. ✅ **step 4's boundary held, and this is the load-bearing check.**

§5 step 4 wrote the tripwire: *"if the runner's `largest gzipped sibling` lands outside
`(119,157 … 126,603)` B, the derivation moves the ceiling and **that is a decision, not a
re-record** — the answer to an object above 139,264 B is a smaller artefact, never a bigger
ceiling."*

**The runner reported 124,177 B. That is inside `(119,157 … 126,603)`.** So the ceiling's
derivation is untouched, `139264` stands, and the outstanding work is a **re-record** and not
a **decision**. Had it landed outside, this section would be saying the opposite and the
correct answer would have been a smaller artefact.

> **AND IT LATER LANDED OUTSIDE — 2026-08-15, and the answer was neither of those two.** The
> console was rebuilt with the LIVE transport and packaged (`sha256 7e49fd5e…`, §4's second
> annotation): `g` is **129,400 B**, which is outside the band above, and the derivation would
> emit **147,456**. **The ceiling was not raised** — that is the half of the sentence above
> that was right and remains binding. **Nor was the artefact cut down**, because it grew for a
> declared reason and was already proven in cloud. **Ruling R10** took the third road: the
> straddle, interface I3 and exactly-one-refusal are the law and are measured true
> (`129,400 ≤ 139,264 < 155,280`, one identity object refused of 57), while the derivation is
> demoted to a dated record of how 139,264 was CHOSEN over the 2026-08-14 tree. **The number
> `139264` still has not moved**, which is the only thing this section ever asked of it, and
> the live figure to watch is the **9,864 B** of gzipped headroom that remains.

**§5's residual doubt was also answered.** Reason 1 for not re-recording was that
`actions/setup-python`'s CPython on `ubuntu-24.04` links zlib 1.3 against 1.3.1 locally, and
`_LARGEST_SERVED_WIRE_BYTES` is the one number that would be sensitive to it. The runner's
124,177 against the workstation's 124,127 is a **50-byte** difference on a ~124 kB object —
consistent with a different `vite` content hash inside the asset, not with a deflate change of
that magnitude. **It is not decomposed here, and it must be before the constant is
re-recorded**: the honest re-record names the run id and the artefact `sha256` beside each
number, which is exactly what step 3 already says.

### 8.4 The `.gitignore` finding was right, and it is now a red lane

The note above — *"`collected.txt` … is the single file failing `scripts/qa/check_reuse.py`,
against two ratchets whose baseline is a hard-gated 0"* — **was a prediction and it has come
true on the board.** `submission` run
[31770005810](https://github.com/Shaugato/mainline/actions/runs/31770005810) at `7535670` is
**red**, on one job, on exactly that file:

```
UNCOVERED — resolve a licence or annotate (1):
    collected.txt
REFUSED [RATCHET] metric=uncovered_total baseline=0 measured=1 [HARD GATE: baseline is 0]
```

Recorded here because this page called it first, and because the cure is the one this page
already named — **delete it or licence it, in the tree** — and not a scope list, not an
exemption, and not a baseline of 1. `docs/CI-STATE.md` §1.0.2 carries the board row.
