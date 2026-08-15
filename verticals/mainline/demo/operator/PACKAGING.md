<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PACKAGING.md — memo to the orchestrator: what shipping the operator surface costs

**Worker:** W8 · **Date:** 2026-08-15 · **Measured on:** node 24.14.0, pnpm 11.5.3, this tree
**Every number below was measured in this session.** No estimates. Where something was not
measured, it says so.

> **HEADLINE — READ THIS FIRST.**
> **R2 does not hold as written, and the reason is benign.** `dist/assets/index-*.js` is **not**
> byte-identical with and without the operator entry: adding a second HTML input causes Rollup
> to hoist Vite's `modulepreload-polyfill` out of the console entry chunk into a **shared
> chunk** that both entries import. The console entry got **smaller** (−577 raw B, −236 gzipped
> B) and the widest object this origin serves therefore got smaller too, so **response-ceiling
> headroom improved rather than degraded**. The cost is one extra 447 B gzipped request on the
> console's critical path. The plan said "if the index chunk moves by one byte, the work stops
> and the orchestrator is told." **This is that telling.** §1 has the evidence; §7 has the
> decision I recommend.

---

## 1 · R2 — the two builds, measured

Both builds are of **this same working tree**; the only difference is the
`build.rollupOptions.input` map. The baseline was produced by temporarily removing the
`operator` input, building, and then restoring `vite.config.ts` and **verifying its sha256
matched the original byte for byte** (`767913f2…`, verified with `sha256sum -c`).

### 1.1 The console entry chunk

| | file | raw bytes | gzip (level 9) | sha256 |
|---|---|---|---|---|
| **without operator** | `assets/index-BDAqHgAu.js` | 490,777 | 138,123 | `69d2b07a33e6c9b1cc09d541361dad87712757ae26d3daa7e490067e83c95d9b` |
| **with operator** | `assets/index-Dif0ht5g.js` | 490,200 | 137,887 | `a8d61429076589ee66d9cf1172541de5eed7ff573c22903d7551fb7e776aa2b2` |
| **delta** | | **−577** | **−236** | **MOVED** |

### 1.2 Why it moved — the mechanism, from the manifests

```
without operator:   index.html  imports: (none)          modulepreload-polyfill inlined into the entry
with operator:      index.html  imports: [_modulepreload-polyfill-B5Qt9EMX.js]
                    operator.html imports: [_modulepreload-polyfill-B5Qt9EMX.js]
```

With one HTML entry Vite inlines the polyfill into that entry. With two, it becomes a shared
chunk (`assets/modulepreload-polyfill-B5Qt9EMX.js`, 771 raw B / **447 gzipped B**) that both
entries import. Nothing of the operator surface entered the console chunk; a shared module left
it. **This is a structural consequence of having two entries at all, not of anything the
operator code imports** — R1's no-shared-imports rule is intact and `check-entrypoints.ts`
confirms no React module is in the operator closure.

### 1.3 What this does to the thing the ceiling actually governs

`static_site.DEFAULT_MAX_RESPONSE_BYTES` is `136 * 1024 = 139,264` and bounds **one response**.
The widest object this origin serves is the console entry chunk, compressed.

| | widest served object (gzip 9) | headroom under 139,264 |
|---|---|---|
| without operator | 138,123 | 1,141 B |
| **with operator** | **137,887** | **1,377 B** |

**Headroom improved by 236 B.** The operator entry itself is 29,906 gzipped B — 109,358 B below
the ceiling, and nowhere near being the widest object this origin serves.
`_MINIMUM_HEADROOM_BYTES` is 1,024 and both builds clear it.

> The gzip method here is **exactly the packer's**: level 9, `mtime 0`, no filename in the
> header (`build_lambda.sh::gzip_bytes`). My numbers are directly comparable to the `.gz`
> siblings the package ships, and they are **not** comparable to Vite's build-log gzip column.

### 1.4 Build determinism

Built three times with the operator entry present. `index` and `operator` sha256 identical all
three times. The build is reproducible on this machine.

---

## 2 · The operator entry closure — the number the new budget bounds

Measured with `check-budgets.ts`'s own method: **sum of per-file `gzipSync(level 9)`** over the
manifest's static closure. (Not a concatenated gzip — that would be smaller and would not be
the number CI compares.)

| member | raw | gzip 9 |
|---|---|---|
| `assets/operator-D24tzVGh.js` | 96,734 | **29,906** |
| `assets/operator-DTSzHtCs.css` | 33,043 | 6,813 |
| `assets/modulepreload-polyfill-B5Qt9EMX.js` | 771 | 447 |
| **closure total** | 130,548 | **37,166** |

**`operator-surface` budget: 37,166 / 139,264 = 27 %.** Confirmed by the gate itself:

```
PASS  evidentiary-shell          139.6 KB gzip  /   220 KB  (63%, 3 files)
PASS  operator-surface            36.3 KB gzip  /   136 KB  (27%, 3 files)
check-budgets: all budgets held.
```

`evidentiary-shell` moved 142,702 → **142,913** gzipped B (+211) — it now includes the shared
polyfill. Against a 225,280 B budget that is 63 %, unchanged in practice.

`check-entrypoints` (new, W1's):

```
ok    index.html       3 asset reference(s)
ok    operator.html    3 asset reference(s)
ok    operator closure  2 file(s), 35 module(s) inside
check-entrypoints: 2 document(s), 6 asset reference(s), all resolved.
```

---

## 3 · The `dist/` census

### 3.1 The controlled comparison — what the operator surface itself costs

Both rows are the **same tree state**, minutes apart, differing only in the `input` map. This is
the comparison that isolates the operator surface's contribution.

| | files | total bytes | sourcemaps | non-map files | non-map bytes |
|---|---|---|---|---|---|
| without operator | 70 | 4,172,927 | 27 / 3,179,549 B | 43 | 993,378 |
| with operator | 76 | 4,806,809 | 29 / 3,676,768 B | 47 | 1,130,041 |
| **operator's cost** | **+6** | **+633,882** | +2 / +497,219 B | **+4** | **+136,663** |

The four new **identity** objects are exactly:

1. `operator.html` (5,097 B)
2. `assets/operator-D24tzVGh.js`
3. `assets/operator-DTSzHtCs.css`
4. `assets/modulepreload-polyfill-B5Qt9EMX.js`

The two new `.map` files are stripped by the packer by default and never reach `web/`.

### 3.2 The current tree — what the orchestrator will actually build

**The tree moved under this measurement while it was being taken.** W7 landed
`verticals/mainline/apps/console/public/` — four files — and Vite copies `public/` into `dist/`
verbatim. Re-measured after that landing:

| | files | total bytes | non-map files | non-map bytes |
|---|---|---|---|---|
| **current `dist/` (with operator)** | **80** | **4,939,185** | **51** | **1,262,417** |

The extra four objects are `memory-loop.js` (47,704 B), `memory-verify.js` (21,861 B),
`memory.css` and `memory.html`. **They are W7's, not the operator surface's**, and they are
listed here so the orchestrator does not attribute their weight to the wrong subject when
re-recording §4.1.

**Everything in §1 and §2 survived the re-measurement unchanged**, which is the point worth
noting: `index-Dif0ht5g.js` still hashes to `a8d61429…`, `operator-D24tzVGh.js` still hashes to
`c4e1789a…`, and both closure gzip totals are identical to the byte. Files under `public/` are
copied verbatim and never enter the module graph, so they cannot move a chunk digest — measured,
not assumed.

---

## 4 · Effect on the `web/` census the packer records

`build_lambda.sh` composes `web/` as: `copytree(dist → web/)` **plus** `copytree(bundle →
web/bundle/)`, then strips `web/**/*.map`, then writes a `<name>.gz` beside every compressible
entry. So the operator surface's contribution is **exactly computable** and is:

| quantity | delta |
|---|---|
| identity objects in `web/` | **+4** |
| `.gz` siblings | **+4** |
| **total `web/` entries** | **+8** |
| identity bytes added | +136,663 B |
| gzipped bytes added | +37,166 B |
| largest identity object | **unchanged subject** — still the console entry chunk |
| largest `.gz` object | **unchanged subject**, and smaller by 236 B |

**I did not run the packer.** Absolute `web/` totals depend on the bundle tree as well as
`dist/`, and running `build_lambda.sh` is the orchestrator's step, not a worker's. The deltas
above are arithmetic over a model read out of the packer's own source, and they are stated as
deltas for that reason.

### 4.1 Which measurement constants would need to follow their subject

**I did not edit any of these, and no worker in this wave may.** They live in
`verticals/mainline/apps/demo-api/tests/test_static_site.py`, which R8 puts off limits. Listed
so the orchestrator can re-record them in one pass after the next real package.

| constant | current | why it moves | direction |
|---|---|---|---|
| `_WEB_ENTRIES` | 138 | +4 identity, +4 `.gz` from the operator surface, **plus 8 more from W7's `public/` assets** (§3.2) | → **146** from this wave's operator work alone; **154** if W7's four land in the same package |
| `_IDENTITY_ENTRIES` | 69 | the four operator objects, **plus W7's four** | → **73** operator-only; **77** with W7's |
| `_LARGEST_SERVED_WIRE_BYTES` | 138,177 | the console entry chunk shrank | **down**; headroom improves |
| `_LARGEST_IDENTITY_BYTES` | 490,950 | same object, fewer bytes | **down** |
| `_SECOND_LARGEST_IDENTITY_BYTES` | 67,049 | **the subject changes** — `assets/operator-D24tzVGh.js` at **96,734 B** is now the second-largest identity object. Measured ranking: `index` 490,200 → **`operator` 96,734** → `surface-CHfQhy2K` 67,094 → `surface-TU1IF0k_` 47,749 | **up**, new object |

The last row is the one worth a second look. It is a measurement, not a bound — it exists so a
silent reshuffle of the chunk graph cannot pass unnoticed. **This is exactly such a reshuffle,
and it is intentional**, so the re-record is the correct response and the reshuffle is
documented here rather than discovered later. The operator chunk sits 42,530 B **below** the
response ceiling and 393,466 B below the object above it, so the refusal stays isolated to one
object exactly as before.

**None of these is a bound.** No bound moves in this wave: `DEFAULT_MAX_RESPONSE_BYTES`,
`_HEADROOM`, `_ROUNDING`, `_RATCHET` and `_MINIMUM_HEADROOM_BYTES` are untouched and none needs
to move, because the direction of travel on the quantity they guard is **favourable**.

---

## 5 · The deploy test lane

Run against this tree, numbers read from `--junitxml` and not from a terminal tail:

```
.venv/Scripts/python.exe -m pytest tests/deploy -q --junitxml=<...>
```

| run | tests | failures | errors | skipped | time |
|---|---|---|---|---|---|
| first (tree at §3.1) | **360** | **0** | **0** | **0** | 47.1 s |
| re-run (current tree, §3.2) | **360** | **0** | **0** | **0** | 66.0 s |

Run twice, before and after the concurrent worker landings, so the green is a property of the
tree the orchestrator will package and not of a tree that briefly existed.

**Nothing in `tests/deploy` regressed.** In particular `test_console_repro.py` passes: W1 wrote
the two HTML entries as root-relative string literals rather than `resolve(here, …)` calls
precisely so that the `_RESOLVE_LITERAL` probe assertion keeps meaning what it says instead of
acquiring two exceptions. That decision is load-bearing and it held.

`test_static_site.py` is **not** in `tests/deploy` — it lives in the demo-api package's own
tests and is where the constants in §4.1 are asserted. It was not run here; those constants are
checked against a **packaged archive**, which only the orchestrator produces.

---

## 6 · THE `--console-transport` FINDING — a decision, handed over

**The operator page is ALWAYS a live client of its origin. There is no replay mode for it and
there is no way to give it one without changing what it is.**

Every value on both screens is fetched at page load from `new URL('/v1/…', location.origin)`;
the ISSUE button really posts and really waits. That is not an implementation choice that could
be swapped — it is the entire claim the surface makes. A replayed operator screen would be a
picture of a permit rather than a permit, which is the one defect that makes the whole exercise
worthless.

**Therefore: a package built `--console-transport replay` would ship a permanently live page
beside a replay console.** One origin, two surfaces, two different truth-telling contracts:

| | MAINLINE console (`/`) | CONTROL OF WORK (`/operator.html`) |
|---|---|---|
| `--console-transport live` | live | live |
| `--console-transport replay` | **replay** | **still live** |

### What is actually at risk

Not correctness — the operator page cannot show a stale value, because it has none. The risk is
**an inconsistent story on one origin**: a judge who opens both and notices that one is replaying
fixtures while the other is hitting the database may reasonably ask which of the two the
project's claims refer to. The answer would be "the live one", and having to say that is worse
than not having to.

### The three options, stated plainly

1. **Build `--console-transport live`.** One origin, one contract, no explanation needed. Both
   surfaces are live clients of the same kernel. Costs whatever live-transport costs the console
   already pays.
2. **Build `replay` and say so on screen.** Ship the mismatch and let the console's own honesty
   chrome carry it. Cheap, but it means a caption in the film has to explain a distinction the
   film gains nothing from.
3. **Ship only `/operator.html` in the film and leave the console out of the story.** The
   founder's ruling already points here — the demo is the software the people in the story use,
   not a tour of the console — but the console still ships at `/` and a judge can still open it.

**W8's recommendation: option 1.** The founder's plan is ~2 minutes of live demo, and the one
sentence we most want to be able to say without qualification is *"everything you just saw came
back from the database."* Option 1 is the only one where that sentence needs no footnote.

**This is the orchestrator's decision and it is not made here.** `operator-systems-plan.md` §7
lists it as unsettled; this memo is the write-up it asks for.

---

## 7 · What I recommend the orchestrator does about R2

R2's *purpose* was to guarantee that the operator surface spends none of the console's
1-kilobyte response-ceiling headroom. **That purpose is served.** Its *letter* — byte-identical
index chunk — is not, and cannot be while two HTML entries share one Rollup graph.

1. **Accept the move, and record why.** The chunk moved because a shared module left it, the
   entry got smaller, and headroom improved. Blocking on the letter of R2 here would trade a
   real improvement for a literal reading.
2. **Re-record the five measurements in §4.1** after the next package, in one pass, from the
   archive rather than from `dist/`.
3. **Note that the console's critical path gained one request.** 447 gzipped B, same origin,
   already in the `evidentiary-shell` budget at 63 %. If that request is judged unacceptable,
   the alternative is two separate Vite builds writing into one `dist/`, which costs a build
   step and a new class of collision — I do not recommend it for 447 bytes.
4. **If R2 is to survive as a written invariant, restate it as what it was protecting:**
   *"the widest object this origin serves must not grow, and the operator entry must import no
   console module."* Both are true today and both are mechanically checked — by
   `_MINIMUM_HEADROOM_BYTES` and by `check-entrypoints.ts` / `boundary.test.ts` respectively.

---

## 8 · Commands, so every number above can be re-run

```bash
CON=verticals/mainline/apps/console

# the two builds (restore vite.config.ts and verify its sha256 after the baseline)
( cd $CON && rm -rf dist && npx vite build )

# the gates
( cd $CON && node scripts/check-budgets.ts && node scripts/check-entrypoints.ts )

# the deploy lane, numbers from junitxml and never from a terminal tail
.venv/Scripts/python.exe -m pytest tests/deploy -q --junitxml=<path>

# claim hygiene over this directory
.venv/Scripts/python.exe scripts/demo/claim_hygiene.py
```

**Not run, and deliberately: `terraform` in any form, any redeploy, any SSM write, any AWS
call, and any commit.** The tree is left for the orchestrator.
