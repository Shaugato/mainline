<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The 63 bytes — the console entry chunk and the ceiling it lives under

**Owner:** worker **P5**, proof-and-polish wave. **Recorded:** 2026-08-16.
**Measurement artefact:** `qa/bundle-headroom.json` (every number below is in it, with its command).
**Binding ruling:** **R3**, `docs/demo/proof-and-polish-plan.md` §1.

---

## 0 · The number, in one paragraph

`static_site.py` refuses any **single** response body over `DEFAULT_MAX_RESPONSE_BYTES`
(`136 * 1024` = **139,264 B**) with a `413`. On 2026-08-15 the largest object this origin
puts on the wire was the console's entry chunk at **138,177 B** gzipped — **1,087 B of
headroom, 0.78 %**. `_MINIMUM_HEADROOM_BYTES` reserves 1,024 of those bytes, so the wave
that wrote the operator screens had **63 bytes** of entry-chunk growth to spend.

It spent none of them. The screens landed as a **second HTML entry** and the console entry
chunk *fell* 245 B, to **137,932 B** — **1,332 B of headroom**. Verdict: **PASS**.

| | before | after | |
|---|---|---|---|
| console entry chunk, on the wire | 138,177 B | **137,932 B** | −245 |
| headroom under 139,264 | 1,087 B | **1,332 B** | +245 |
| second-largest wire object | 18,263 B | 29,906 B | the operator entry, new |
| HTML entries | 1 | 2 | `index.html`, `operator.html` |

**What is left, for anyone still editing the console.** The CI gate refuses at 138,240 B
and prints its own margin on every run: **337 B left** over today's `dist/` (Node's zlib;
353 B by the packer's, 308 B in the deploy-env build — see §3 on the two compressors). Call
it **~300 bytes**. That is the number to ask about before adding anything to the console's
static closure — and unlike the 63 bytes, it is now *enforced* rather than remembered: the
build goes red before the origin does. Anything that does not fit belongs behind a lazy
import or in its own HTML entry, where there is ~120 KB.

---

## 1 · What crossing costs, which is the only reason this document exists

When the entry chunk passes the ceiling, the origin answers **`413` to its own entry
JavaScript, for every browser**. `GET /` still answers `200` with the shell — 4,655 B in
the package that ships today, 4,749 B in the console this wave produced, both measured. The
shell fetches its only module, receives a JSON problem document, and **the judge is looking
at a blank page.**

That is a *total* outage of the demo URL, not a slow one, and **it arrives with no warning
from production**, because the shell keeps answering `200` and every health check keeps
passing. Nothing in the deployment can tell you it happened. Only a guard on the build can.

---

## 2 · This is an ENTRY CHUNK problem, not a bundle problem

The sentence the other leads needed, and the reason two screens fitted into 63 bytes:

> The second-largest served object is **18,263 B**. A lazy chunk or a second HTML entry has
> roughly **120 KB** of room. The shared `assets/index-*.js` has 63 bytes.

The ceiling is **per object**. It does not care what the bundle weighs in total; it cares
what the widest single response weighs. So the fix for "this surface does not fit" is never
"make the surface smaller" and never "raise the ceiling" — it is **move the surface off the
entry chunk**, at which point it has six figures of room.

CONTROL OF WORK is the proof: 96,734 identity bytes of operator screens ship as
`assets/operator-*.js`, a **29,906 B** wire object of its own, and no browser that opens the
console pays for a byte of it.

**And the old budgets could not see any of this.** Every budget in
`verticals/mainline/apps/console/budgets.json` was a **sum over a closure**. Measured in one
run on 2026-08-16: `evidentiary-shell` reported **63 %** of its 220 KB threshold while the
entry chunk inside that same closure sat at **99.0 %** of the wire ceiling. A budget at 63 %
would have passed the build that took the demo dark.

---

## 3 · How the number is measured, and why the `after` figure is not a guess

**Read the archive, never `console/dist`.** Only `out/lambda/mainline-demo-api-arm64.zip`
carries the `.gz` siblings the origin actually serves; `dist/` is the packer's *input*.

```
.venv/Scripts/python.exe -c "import zipfile;z=zipfile.ZipFile('out/lambda/mainline-demo-api-arm64.zip');print(max((i.file_size,i.filename) for i in z.infolist() if i.filename.startswith('web/') and i.filename.endswith('.gz')))"
```

No archive was built in this sitting, and that was deliberate: building one would have
overwritten the deploy artefact from a `dist/` whose compiled `buildId` is `dev`, which is
not what the orchestrator deploys. So the `after` figure was measured over the packer's
**input** tree using the **packer's own gzip function**, lifted verbatim from
`scripts/deploy/build_lambda.sh:664-692` — level-9 raw deflate in a hand-written RFC 1952
container with no clock and no OS byte.

**That function was falsified against the artefact that ships.** All **69** identity objects
in `sha256 7c97b532…` were re-compressed with it and compared to the sibling the packer had
written beside each: **69 of 69 byte-identical**, not merely equal in length. The `after`
figure is therefore the number the next archive's central directory will carry for that
tree, not an estimate of it.

The build was also re-run with the variables the deploy supplies —
`VITE_MAINLINE_API_BASE=/` and `MAINLINE_BUILD_ID=<sha>` — because both reach the emitted
bytes. They cost **+173 identity B / +45 wire B**. Use PowerShell, never Git Bash: MSYS
rewrites a bare `/` argument into a path on the workstation
(`docs/deploy/console-build.md` §1).

### One honest caveat: two zlibs

CI measures with **Node's** zlib (1.3.1-e00f703); production compresses with **CPython's**.
Across all 51 compressible objects the largest disagreement is **110 B**
(`assets/worker-*.js`: Node 15,692, packer 15,582); on the entry chunk it is **16 B**. The
1,024 B reserved between the CI budget and the ceiling is **9.3×** that, so a Node-measured
pass at 138,240 B implies a packer-measured size of at most 138,350 B — still 914 B under
the ceiling. **The guard cannot be fooled by the compressor.**

---

## 4 · The three guards, and what each one catches

| where | what it catches | when it runs |
|---|---|---|
| `budgets.json` → `wire_ceiling`, **138,240 B**, `measure: largest_object` | the widest single object crossing 139,264 − 1,024 | `pnpm run ci`, on `dist/`, **before anything is packed** |
| `budgets.json` → `forbidden_in_entry` rows scoped with `in` | the *cause*: `src/operator/` becoming statically reachable from `index.html` | same run, from the sourcemaps |
| `test_static_site.py` → `_assert_headroom` | the built package inside the margin | pytest, wherever an archive exists |
| `test_static_site.py` → `test_the_console_ci_budget_goes_red_before_the_origin_does` | somebody loosening `budgets.json` instead of fixing the chunk | pytest, everywhere, no build needed |

`138,240 = 139,264 − 1,024`. The last row is the **weld**: it asserts that equality, so the
two files cannot drift apart and neither can be loosened alone.

### Why `wire_ceiling` is its own key and not a fourth row in `budgets`

`src/perf/budgets.ts` mirrors the `budgets` array — it is the console's D13 performance
contract, six budgets, three of them with CPU-throttle conditions — and
`tests/unit/perf/budgets.test.ts` asserts the two **id sets are equal**. A fourth row there
is a vitest failure until that mirror and its `expect(BUDGETS.length).toBe(6)` are edited,
and neither file belongs to this gate.

It would also have been *untrue*. A performance budget answers "how long does a supervisor
wait"; this number answers "**what does the origin refuse**", and its authority is
`static_site.py`, not `ui.md`. So it is filed as its own required gate, read **first** by
`check-budgets.ts`, whose **absence is a failure** — being outside the array costs it no
teeth. `pnpm exec vitest run tests/unit/perf/budgets.test.ts`: 11 passed.

**Each of these has been seen to go red** (`qa/bundle-headroom.json` → `verification.falsifications`):

* entry chunk padded by 400 incompressible bytes → `assets/index-*.js is 138599 B gzipped
  — 359 B OVER the 138240 B wire budget`, exit 1. Note **138,599 is still 665 B below the
  production ceiling**: the guard fires while the origin is still serving every object it
  has, which is the entire design.
* a `src/operator` module injected into the console entry's sourcemap → `"src/operator/" is
  bundled INTO the static closure of "index.html"`, naming the module, exit 1.
* the `operator.html` manifest key renamed → the operator budget cannot be measured **and**
  `no chunk matched the root "operator.html", so every forbidden_in_entry row scoped to it
  was NOT checked`. A ban whose subject was renamed goes red rather than quiet.
* the `wire_ceiling` key deleted → `NOTHING in this run measures the widest SINGLE object
  the origin has to serve`, exit 1. A gate that can be disabled by deleting it is not a gate.
* `wire_ceiling.max_gzip_bytes` loosened to 139,264 → `assert 139264 == (139264 - 1024)` in
  pytest. `budgets.json` was restored byte-for-byte after every one of these.

### What these guards do NOT see

`dist/memory.html`, `dist/memory-loop.js` and `dist/memory-verify.js` are hand-written
`public/` assets, so the Vite manifest — and therefore `check-budgets.ts` — cannot see them.
The largest is 16,023 wire bytes, four figures below the ceiling, and the archive-level
assertions in `test_static_site.py` are what cover them. A guard's blind spot is part of the
guard, so it is written down here.

---

## 5 · When it goes red, this is the fix

**In order. None of these is "raise a number".**

1. **Read which chunk.** `check-budgets.ts` names it: `widest of N: assets/…`. If the name
   is not `index-*.js`, this is not the outage case — a lazy chunk over the ceiling is a
   broken feature, not a blank page.
2. **Find the static edge.** The entry chunk grew because something became statically
   reachable from `src/main.tsx`. `node scripts/check-budgets.ts` prints the module count in
   the entry closure; the sourcemap `sources` array of the entry chunk is the full list.
3. **Move it behind a lazy boundary.** `const X = lazy(() => import('./X'))` — the surface
   becomes its own chunk with ~120 KB of room, and the entry chunk pays only for the import
   site.
4. **Or give it its own HTML entry**, as `operator.html` already is: add it to
   `rollupOptions.input` in `vite.config.ts`, give it a budget row, and add a
   `forbidden_in_entry` row with `in` naming the entry it must not leak into.
5. **Then re-measure** and update `qa/bundle-headroom.json`.

---

## 6 · What may never move (ruling R3)

* `DEFAULT_MAX_RESPONSE_BYTES` = `136 * 1024`
  (`verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py:323`)
* `_MINIMUM_HEADROOM_BYTES` = `1024`
  (`verticals/mainline/apps/demo-api/tests/test_static_site.py:992`)
* `wire_ceiling.max_gzip_bytes` = `138240` (`budgets.json`)

Not in either direction, for any reason. Raising a ceiling so the arithmetic agrees is the
move that put this constant at 2 MiB and then at 512 KiB, and it is exactly what the
regression guard's BOUNDS family exists to catch. Three guards in two languages now go red
on it.

`_LARGEST_SERVED_WIRE_BYTES` **is** a measurement, and is the one number in that file that
moves — re-recorded from a freshly built archive with the sha256, the
`--console-transport` setting and the `MAINLINE_BUILD_ID` beside it, exactly as the
existing comment block does.

---

## 7 · For whoever rebuilds and deploys

The archive on disk (`sha256 7c97b532…`) is the **previous** console: one HTML entry, no
`operator.html`. **It must be rebuilt before deploy** or the demo URL serves a console
without the screens the film is shot on.

When it is rebuilt, these are measurements and must be re-recorded from the new archive's
central directory — re-recording them is not moving a bound
(`test_static_site.py:879-895`): `_LARGEST_SERVED_WIRE_BYTES`, `_LARGEST_IDENTITY_BYTES`,
`_SECOND_LARGEST_IDENTITY_BYTES`, `_WEB_ENTRIES`, `_IDENTITY_ENTRIES`, and the object named
in the `refused` dict of
`test_serving_the_deployed_package_derives_the_ceiling_end_to_end`.

**Predicted shape**, recorded so a surprise is visible: **154** web entries / **77**
identity / **77** siblings, where today's archive is 138 / 69 / 69. The archive's own
central directory is what gets recorded; this is only a prediction.

---

## 8 · One observation, recorded and not chased

The wave brief reports mojibake in `budgets.json` and `evidence/tool-usage/*.json` — em
dashes stored as an `a-euro-"` sequence. **Measured: there is none.** All three files decode
as clean UTF-8, and their only non-ASCII characters are `U+2014` (4 / 42 / 23), `U+00A7`
(2), `U+2022` (1) and `U+2264` (2). Zero occurrences of the mojibake byte sequence in any of
them.

The cause is the **Windows console code page**, not the files: printing those characters to
a cp1252 stdout raises `UnicodeEncodeError` or renders replacement glyphs — reproduced in
this sitting, and fixed for reading with `python -X utf8`. **Nothing was re-encoded.**
Re-encoding a clean file to satisfy a terminal would corrupt it.
