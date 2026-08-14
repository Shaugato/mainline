<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The response ceiling and the tree it governs: the DEPLOYED tree is authoritative

**Worker:** `w4-response-ceiling` · **Measured 2026-08-14 on TRAPPOINT**, HEAD `e944407`
(working tree dirty — six workers writing concurrently)
· **Interpreter:** `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`
· **Ruling implemented:** `docs/leads/suite-green-plan.md` §3.4 and §3.5
· **Artefact read:** `out/lambda/mainline-demo-api-arm64.zip`, built 2026-08-13 15:54,
  7,646,264 B on disk
· **Files changed:** `verticals/mainline/apps/demo-api/tests/test_response_contract.py`,
  `verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py`, this file

**`DEFAULT_MAX_RESPONSE_BYTES` did not move.** It is still `136 * 1024 = 139,264`. What
moved is `test_response_contract.py`'s declarations, which had been measured over the
packer's **input** tree. This document is the arithmetic that settles which side was the
derived one.

> **UPDATED 2026-08-15 · worker `w5-ceiling-and-cost-re-record`** (HEAD `3933b97`, working
> tree dirty — six workers writing concurrently). Two things happened and both are below:
> the derivation table in §2 was **re-read from the package on disk** (`sha256 12fcba7a…`)
> and now names `assets/index-DzVoV1YM.js`, with the 2026-08-14 figures struck rather than
> deleted; and the LIVE console rebuild this wave calls for was built, measured, and found
> to put the largest served object **outside** the window in which `139,264` is derivable.
> **The ceiling was not moved. §9 is the STOP, with the measurement.** Also re-recorded, to
> the same package: `tests/deploy/test_furl_compression.py`, which had been pinned to a
> console two builds old and was erroring in fixture setup on all thirty of its cases.
> `DEFAULT_MAX_RESPONSE_BYTES` still did not move.

> **UPDATED AGAIN 2026-08-15 · worker `w5-decision-record`** (HEAD `3933b97`, working tree
> dirty). **The STOP in §9 is RESOLVED.** The lead ruled — `docs/leads/reconcile-constants-plan.md`
> §1, ruling **R10** — and **`DEFAULT_MAX_RESPONSE_BYTES` still did not move**: it is
> `136 * 1024 = 139,264`, byte-identical, unraised. What moved is the *status of the
> derivation*, which is now dated provenance rather than a live assertion. **§9 is not
> withdrawn and not rewritten**; §10 is the resolution, §10.7 corrects §9's figures to the
> package that actually shipped, and §2.2 gains the fourth column §9.4 asked the resolving
> worker to add — read from `out/lambda/mainline-demo-api-arm64.zip`, `sha256 7e49fd5e…`,
> built `--console-transport live`.

---

## 1 · The question, and why it is not a matter of taste

The ceiling governs what this origin **costs**. Two trees could be called "the web tree":

| | files | bytes | source maps | `.gz` siblings |
|---|---:|---:|---:|---:|
| the packer's **input** — `console/dist` + `console/fixtures/bundles/demo-cloud` | 75 | 3,571,990 | 18 | 0 |
| the **deployed** package — `web/` inside `mainline-demo-api-arm64.zip` | 114 | 1,274,342 | 0 | 57 |

**Ruling: the deployed tree.** Cost is incurred by bytes leaving the deployed origin, so an
object that never reaches the deployed package cannot be evidence about a cost control.
`build_lambda` strips `web/**/*.map` by default, so the eighteen source maps in the input
tree are absent from the deployment **by construction**. A ceiling justified by refusing
them would be a ceiling justified by refusing objects that are not there — which is
precisely the error the previous value (512 KiB) was made of, one octave down from the
error before that (2 MiB).

### 1.1 · The tiebreaker came from a third artefact, not from either side

The no-shortcut rule says: when a test and the code disagree, ask which side is
AUTHORITATIVE. Here the deciding evidence sits in **neither** file in dispute.
`verticals/mainline/apps/demo-api/tests/test_static_site.py` §(f) — a sibling module,
written by a different wave — already derives interface I3 over this same package, and
already names this file's behaviour as the mistake, in writing at lines 819–824:

> the packer's input tree … *which is what `test_response_contract.py` falls back to* … is
> 75 pre-strip files with 18 source maps and zero siblings, so a derivation measured there
> would be measured over bytes that no longer deploy.

So two test modules in one suite declared **different values for one quantity** — "the
largest object the origin serves" was 433,396 B in `test_response_contract.py` and
124,127 B in `test_static_site.py`. One of them had to be wrong, and the artefact settles
which.

---

## 2 · The measurement, re-derived rather than transcribed

Read from the zip's central directory — no unpacking, so the numbers are the packaged
sizes and not whatever a checkout happens to hold. Reproduce with:

```
python -c "import zipfile; z=zipfile.ZipFile('out/lambda/mainline-demo-api-arm64.zip'); \
  w=[i for i in z.infolist() if i.filename.startswith('web/') and not i.is_dir()]; \
  print(len(w), sum(i.file_size for i in w))"
```

**SUPERSEDED — the reading of 2026-08-14**, kept verbatim rather than deleted, because the
arithmetic of §2.1 was originally done over it and a derivation whose input has been quietly
replaced is a derivation nobody can check:

```
[SUPERSEDED 2026-08-14]
web/ entries        114 files   1,274,342 B
  identity objects   57 files     985,030 B
  .gz siblings       57 files     289,312 B
  source maps         0 files           0 B

largest identity        433,396 B  assets/index-BjAGxrVJ.js
second-largest identity  51,266 B  assets/surface-Csi7pmRe.js
largest .gz sibling     124,127 B  assets/index-BjAGxrVJ.js.gz
```

**RE-READ 2026-08-15** over `out/lambda/mainline-demo-api-arm64.zip`, `sha256
12fcba7ad69b2ffe8240b1ecbf763744d9441e12309109f7fab88ac62dfbcc27` — the package that is on
disk and that the live Function URL is serving (it answers `GET /` with the same 4,655 B
`index.html` this zip carries, referencing the same chunk name):

```
web/ entries        114 files   1,274,743 B
  identity objects   57 files     985,306 B
  .gz siblings       57 files     289,437 B
  source maps         0 files           0 B

largest identity        433,564 B  assets/index-DzVoV1YM.js
second-largest identity  51,266 B  assets/surface-BcxWkbKu.js
largest .gz sibling     124,177 B  assets/index-DzVoV1YM.js.gz
index.html                4,655 B

orphan .gz siblings (no identity object):  0
identity objects with no sibling:          0
identity objects over 139,264 B:           1  -> ('assets/index-DzVoV1YM.js', 433564)
.gz siblings over 139,264 B:               0  -> ()
```

The 2026-08-14 block and this one describe **two different console builds of the same
shape** — the chunk name is content-hashed, so it moves whenever the source does. The shape
did not move: 114 entries, 57 + 57, no orphans, no gaps, no maps, exactly one object over
the ceiling.

Every figure the lead published reproduces. **Because every identity object has a sibling
and no sibling is an orphan, the bytes a browser pulls are the compressed column
throughout**, so `largest_served_wire_bytes = 124,177` — not 433,564.

### 2.1 · Interface I3, applied

> `largest_served_wire_bytes <= ceiling < 1.20 x largest_served_wire_bytes`, and within that
> window the ceiling is the smallest multiple of 8 KiB at or above
> `1.10 x largest_served_wire_bytes`.

~~Over the 2026-08-14 reading (`g = 124,127`): `1.10 x g = 136,539.7`, next 8 KiB boundary
`17 x 8,192 = 139,264`, `139,264 / 124,127 = 1.121948… -> 1.122`.~~ Re-derived 2026-08-15
over the package above:

```
1.10 x 124,177                     = 136,594.7
smallest 8 KiB multiple >= that    = 17 x 8,192 = 139,264 = 136 KiB
139,264 / 124,177                  = 1.121495…  -> 1.121, inside the 1.20 ratchet
124,177 <= 139,264                 -> the origin can still serve its own site
```

**The rounding is what makes this stable.** 124,127 and 124,177 are different measurements
and both land on 136 KiB, because the 8 KiB step absorbs 50 bytes without anybody having to
decide anything. That is the derivation doing its job, and it is also why the window in §9
is worth writing down: the step absorbs a range, and outside that range it does not.

**`DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024` is a consequence of those three lines, not an
input to them. It does not move.**

> **SUPERSEDED AS A LIVE DERIVATION, 2026-08-15, by ruling R10 (§10). The number is not
> superseded; its tense is.** The arithmetic above is preserved as the dated record of how
> 139,264 was **chosen**, over `g = 124,177` in package `12fcba7a…`. Over the package that
> ships today (`sha256 7e49fd5e…`, `g = 129,400`) the same formula emits **147,456**, and
> R10 declines to follow it: the ceiling is **kept** by the invariant it was always for —
> `0 < 129,400 < 139,264 < 457,123`, exactly one identity object refused — rather than
> re-emitted by the formula. **The ceiling itself did not move by one byte.** §10 is the
> ruling and the argument; §10.6 carries the number that now warns instead of the window.

### 2.2 · The declarations that follow, and the arithmetic for each

The struck column is the input-tree error this ruling corrected; the second is the
2026-08-14 deployed reading it corrected to; the third is the 2026-08-15 re-read of package
`12fcba7a…`. The right-hand column — **the fourth column §9.4 asked whoever resolved R4 to
add** — is the **package of record that ships today**: `out/lambda/mainline-demo-api-arm64.zip`,
`sha256 7e49fd5e…`, built `--console-transport live` with `MAINLINE_BUILD_ID=3933b97`. Every
figure in it was read out of that zip's central directory by `w5-decision-record` on
2026-08-15, not copied from a plan, and it is what the code declares under ruling **R10**
(§10).

| declaration | ~~was (input tree)~~ | was (deployed, 2026-08-14) | was (package `12fcba7a…`, 2026-08-15) | **is (package of record `7e49fd5e…`)** | derivation |
|---|---|---|---|---|---|
| `_LARGEST_WEB_OBJECT` | ~~`assets/index-BjAGxrVJ.js.map`~~ | `assets/index-BjAGxrVJ.js` | `assets/index-DzVoV1YM.js` | **`assets/index-DJX27H0M.js`** | `max(identity)` over the zip |
| `_LARGEST_WEB_OBJECT_BYTES` | ~~1,554,168~~ | 433,396 | 433,564 | **457,123** | same |
| `_LARGEST_SERVED_OBJECT_BYTES` | ~~433,396~~ | 124,127 | 124,177 | **129,400** | `max(sibling)`; every object has one |
| `_WIDEST_SERVED_IDENTITY` | ~~—~~ | `assets/surface-Csi7pmRe.js` | `assets/surface-BcxWkbKu.js` | **`assets/surface-COD-Iou0.js`** | second-largest identity |
| `_WIDEST_SERVED_IDENTITY_BYTES` | ~~—~~ | 51,266 | 51,266 | **51,266** | unchanged across all three builds |
| `_REFUSED_BY_THE_CEILING` | ~~`('…js.map',)`~~ | `('assets/index-BjAGxrVJ.js',)` | `('assets/index-DzVoV1YM.js',)` | **`('assets/index-DJX27H0M.js',)`** | identity objects `> 139,264` |
| headroom | ~~90,892~~ | 15,137 | 15,087 | **9,864** | `ceiling − largest served` |
| cut | ~~3.586~~ | 3.4916 | 3.4915 | **3.5326** | `largest identity / largest served` |
| tree totals | ~~`(75, 3,571,990)`~~ | `(114, 1,274,342)` | `(114, 1,274,743)` | **`(114, 1,308,543)`** | central directory |
| `.gz` sibling total | ~~0~~ | 289,312 | 289,437 | **295,731** | central directory |
| I3 ratio | ~~—~~ | 1.122 | 1.121 | **1.076** | `ceiling / largest served` |

**`DEFAULT_MAX_RESPONSE_BYTES` does not appear in this table**, and that is the point of the
table: every row above is a description of an artefact, and the ceiling is a consequence of
the rule applied to one of them. It has been `136 * 1024 = 139,264` across all four
columns — including the last one, where the derivation no longer re-emits it and the
invariant keeps it anyway (§10).

Two of these deserve saying out loud.

**The refusal set is not the measured list pasted in.** The input tree's measured refusal
list is `['assets/index-BjAGxrVJ.js', 'assets/index-BjAGxrVJ.js.map',
'assets/surface-CVAkDJuP.js.map', 'assets/surface-Csi7pmRe.js.map',
'assets/worker-BP2nXQVE.js.map']` — five entries, which is what the failing test printed.
The ruling's list is **one** entry. The three maps are gone because the packer strips them,
not because a run happened not to print them. The two lists differ, which is the test that
this is a ruling being implemented rather than an expectation being fitted to output.

**`cut` is 3.4915, not 3.586, not 3.4917, and no longer 3.4916.** The old 3.586 was
`1,554,168 / 433,396` — the source-map strip's cut, a different pair of numbers entirely, and
keeping it would have been comparing a pre-strip artefact to a post-strip one. ~~The
2026-08-14 figure was `433,396 / 124,127 = 3.491553…`, which is **3.4916** to four places.~~
~~Over the package on disk today it is `433,564 / 124,177 = 3.491500…`, which is **3.4915** to
four places, and that is what `test_response_contract.py` asserts.~~ **Re-measured
2026-08-15 over the package of record `7e49fd5e…`: `457,123 / 129,400 = 3.532635…`, which is
3.5326 to four places** — the figure in the fourth column above and the one the code
declares under R10. `cut` is a **measurement**, not a bound: it is what the compression the
packer already performs buys on the largest object, and it moves whenever the console does. **The lead's §3.4 prose
says 3.4917.** That is a fifth-significant-figure rounding slip in a derived display value,
not a fact about the tree; it does not touch the I3 derivation, the ceiling, or the refusal
set, and the ruling stands. The code asserts the derived value and this paragraph is the
record that the three differ, because silently shipping one figure under a ruling that says
another is the kind of small unexplained divergence that costs an hour later.

---

## 3 · The two hazards, handled rather than routed around

### 3.1 · A `.gz` sibling has no URL, so its 404 is not a refusal

Interface I1: a direct request for any path ending `.gz` is a **404**. Enumerating all 114
`web/` entries and collecting every non-200 files 57 404s as "refusals" and reports a
control that refuses **one** object as one that refuses **fifty-eight**. Three separate
guards now exist, at three different levels:

1. **At the declaration** — `test_the_ceiling_refuses_something_it_governs` fails if any
   name in `_REFUSED_BY_THE_CEILING` ends `.gz`.
2. **At the enumeration** — the sweep walks identity objects only and asserts
   `len(identity) == 57`.
3. **As its own property, with a negative control** —
   `test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal` asserts
   all 57 siblings answer 404 `asset_not_found`, and then **performs the naive whole-tree
   sweep on purpose**, shows it yields 58 non-200s, and separates the 57 404s from the 1
   413. Without that last block, "the enumeration covers identity objects" is a convention a
   refactor can undo with nothing going red. Mutating the sweep to walk all 114 entries was
   verified to turn the test red.

### 3.2 · The tree is a build output, and the skip must not be able to pass vacuously

The tests read `out/lambda/mainline-demo-api-arm64.zip`, which is `.gitignore`d (line 9).
`_require_built_tree()` skips with a reason that names the file and the command that builds
it. **It is not softened into a silent skip, and the section cannot go green by skipping:**
two assertions take no tree at all and run everywhere —
`test_the_ceiling_refuses_something_it_governs` (the anti-vacuity assertion: an empty refusal
set fails by construction) and
`test_the_declared_numbers_straddle_the_ceiling_rather_than_sitting_under_it` (the I3
arithmetic). Measured with the package renamed away: **45 passed, 5 skipped**, and both
anti-vacuity assertions among the 45.

### 3.3 · The input-tree fallback is deleted, not demoted

`_web_tree_sources()` used to fall back to `console/dist` + the evidence-bundle fixture. That
fallback is removed. A fallback that answers a cost question with the wrong tree is worse
than no answer: the skip says the assertion did not run, which is true and actionable,
whereas the fallback said it ran and passed.

**This costs no CI coverage.** No Python lane in `.github/workflows/` builds the console or
the package — `ci.yml` and `cluster-tests.yml` contain no `pnpm` step and nothing writes
`out/lambda` — so these assertions already skipped in CI before this change and still do.
What changed is that a developer box holding a stale `console/dist` can no longer report a
green that means nothing.

---

## 4 · §3.5 — the base64 test encodes a superseded metric, and what replaced it

`test_base64_inflation_is_measured_and_not_assumed` asserted that 3,300 B of non-UTF-8 under
a 4,096 ceiling answers **413**, because base64 inflates it to 4,400. It now answers **200**.

That is a ratified interface change, and it was ratified **outside the module that changed**
— `docs/leads/cost-finish-plan.md`, interface **I2**: the ceiling is measured on WIRE bytes
because a Function URL decodes `isBase64Encoded` before anything leaves and AWS bills what
leaves. Had that ratification lived only in `static_site.py`'s own docstring, the module
would have been marking its own homework and **the test would have been the authoritative
side.**

**The rewrite is not `assert 200`.** It refuses four real failure modes:

1. **The inflation is still measured.** 3,300 B in, exactly 4,400 characters out, and
   `4 x ceil(n/3)` is shown to reproduce it. That formula is validated here because part 4
   depends on it.
2. **The ceiling is applied to the DECODED length.** The case still straddles —
   `3,300 < 4,096 < 4,400` — and the straddle is asserted *before* the status, so a case
   that stopped straddling fails as "this test stopped testing" rather than as an
   uninterpretable status mismatch. Falsified by inverting `_wire_bytes` to weigh the
   envelope: red.
3. **The decoded length is computed, never decoded.** `_wire_bytes` runs on every response
   the module emits, so a decoding version allocates a second copy of every body. This is a
   structural claim and is checked as one, over the function's AST. Falsified by rewriting
   `_wire_bytes` as `len(base64.b64decode(body))`: red.
4. **The ENCODED payload stays under Lambda's response-payload quota.** This is the one
   bound in this module's world that really is measured on the base64 string, and **nothing
   in this repository asserted it before 2026-08-14.** At the default ceiling the widest
   payload `_file` can construct is `4 x ceil(139,264 / 3) = 185,688` characters against
   `LAMBDA_RESPONSE_PAYLOAD_BYTES = 6,000,000` — a factor of 32.3.

**Falsifiability of part 4, which is the part most at risk of being a tautology.** The
assertion fails whenever the ceiling exceeds three quarters of the quota, and the test says
so by computing that case: at a 5 MiB ceiling the same arithmetic yields 6,990,508 and
breaches the quota. Raising `DEFAULT_MAX_RESPONSE_BYTES` to `5 * 1024 * 1024` was verified to
turn the test red.

**On the constant's value.** AWS documents the quota as "6 MB" without disambiguating, so
`6,000,000` and `6 x 1024 x 1024 = 6,291,456` both have a claim. The **smaller** reading is
declared, because it is the conservative side of an ambiguity this repository does not get to
resolve. At 32x margin nothing turns on the choice except that it is made in the safe
direction and said out loud. Nothing enforces the quota at runtime and nothing should: at
this ceiling it is a branch no input can reach.

---

## 5 · Which side I moved, and why that side was the derived one

**I moved the DECLARATIONS in `test_response_contract.py`.** They are the derived side
because:

* the deployed artefact is a fact and the declarations are a description of it;
* the declarations were measured over a tree the deployment does not contain, so they were
  never a description of the thing the control governs;
* a sibling test module had already derived the opposite values from the authoritative
  artefact, and two modules cannot both be right about one quantity;
* every new number is **recomputed from the zip and the I3 formula in the test itself** —
  `1.10 x 124,127` → next 8 KiB boundary → 139,264 appears as executable arithmetic, not as
  a transcribed constant.

**I did not move `DEFAULT_MAX_RESPONSE_BYTES`,** which is the authoritative side here: it is
the consequence of a written rule applied to a measured artefact, and it was already correct.

**Change to `static_site.py`, in full:** one entry added to `__all__`, one new module
constant `LAMBDA_RESPONSE_PAYLOAD_BYTES`, and prose. Proven inert rather than asserted inert:
reversing the two code edits and comparing the module's AST with docstrings stripped leaves
**exactly** the `__all__` string and the one `AnnAssign` as the difference. No function body,
no branch, and no existing value changed.

---

## 6 · Falsification log

Every mutation below was applied, run, and reverted. A mutation that left the suite green
would be a test that cannot disagree with its code.

| mutation | node that must go red | verdict |
|---|---|---|
| declare a `.gz` sibling as a ceiling refusal | `…refuses_something_it_governs` | RED |
| empty `_REFUSED_BY_THE_CEILING` | `…refuses_something_it_governs` | RED |
| declare a source map as refused | `…refuses_something_it_governs` | RED |
| ceiling back to 512 KiB | `…straddle_the_ceiling…` | RED |
| ceiling to 5 MiB (breaches the payload quota) | `…base64_inflation…` | RED |
| `_wire_bytes` weighs the ENVELOPE (I2 inverted) | `…base64_inflation…` | RED |
| `_wire_bytes` decodes rather than computes | `…base64_inflation…` | RED |
| declare the served maximum as 433,396 (pre-ruling) | `…straddle_the_ceiling…` | RED |
| declare the input tree's totals `(75, 3,571,990)` | `…matches_the_shape…` | RED |
| sweep all 114 entries instead of 57 identity objects | `…serves_or_is_a_declared_refusal` | RED |
| package renamed away | 5 skip loudly; 45 pass, **both anti-vacuity assertions among them** | as designed |

---

## 7 · What this does NOT establish

* **It is not a spend bound.** Lambda bills a 413 as it bills a 200, so the ceiling bounds
  bytes per response and nothing about invocation charge. The spend bound is the cost-guard
  responder.
* **It does not run in CI.** No Python lane builds the package, so the tree-reading half of
  section (c) skips there. The declaration-only half runs everywhere, which is why the
  anti-vacuity assertion was deliberately built to need no tree.
* **The declarations are pinned to one build.** `assets/index-DzVoV1YM.js` is a
  content-hashed name; rebuilding the console changes it and every equality in section (c)
  goes red at once, naming what to re-derive. That is the ratchet working, not a defect —
  but it means these numbers describe the package `sha256 12fcba7a…dfbcc27` and nothing
  later. ~~The same sentence was written about `assets/index-BjAGxrVJ.js` and the artefact of
  2026-08-13 15:54; that build has since been superseded, exactly as predicted here.~~ It
  has now happened twice, and §9 is the third time coming. **The third time arrived on
  2026-08-15**: the package of record is `sha256 7e49fd5e…`, its entry chunk is
  `assets/index-DJX27H0M.js` at 457,123 B, and §10 is the ruling under which the
  declarations are re-recorded to it — the ratchet working for the third time, still not a
  defect.

## 8 · Stale against this ruling, owned by others, not touched

* `docs/deploy/COST-BOUND.md:149` declares interface **I4** as *"Largest response the origin
  can emit: **1,554,168 B** — `web/assets/index-BjAGxrVJ.js.map`"*, sourced to `zipfile` over
  `out/lambda/mainline-demo-api-arm64.zip`. **The zip contains zero source maps.** Line 151
  declares I6 as *"3,571,990 B over 75 files under `web/`"*, which is the packer's input
  tree, not the package. Both are the input-tree error this ruling corrects, in the document
  the ceiling is quoted from. The same file's then/now table at line 45 already gives the
  *now* as **124,127 B on the wire (gzip sibling)** and line 42 says the package holds **0**
  source maps — so the document's summary agrees with this ruling while its interface table
  still carries the superseded figures. One of the two has to move, and it is not the
  summary.
* `docs/leads/cost-bound-plan.md:25,28` carry the same two figures with the same sourcing.
* `docs/deploy/LATENCY.md` measures an `asset_map` beat against
  `GET /assets/index-BjAGxrVJ.js.map`, an object the deployed origin answers **404** to.
* **Found 2026-08-15, and new to this list:** `docs/deploy/lambda-bundle.md:215` publishes
  the sibling inventory as `57 | 289 312`, and
  `verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py:83,245` repeats
  `57 identity objects (985,030 B)` and `57 siblings (289,312 B)` in prose. The package on
  disk carries **985,306 B** and **289,437 B**. Neither file is owned by a worker in the
  package-and-verify wave, so both are reported rather than edited — but the module
  docstring of the code that *implements* the ceiling now disagrees with the code's own
  test declarations, which is the shape of drift this document exists to stop.

---

## 9 · STOP — the LIVE rebuild leaves the derivation window (2026-08-15)

**Ruling R4** of `docs/leads/package-and-verify-plan.md` fixes the range of `g` (the gzipped
bytes of the largest served object) over which the derivation
`ceil(floor(1.10·g) / 8192) · 8192` returns the authoritative `139,264`:

```
119,158  <=  g  <=  126,604
```

Re-derived independently here rather than quoted. For the result to be `17 × 8,192`,
`floor(1.10·g)` must fall in `(16 × 8,192, 17 × 8,192] = (131,072, 139,264]`; the left end
gives `g ≥ 131,073 / 1.10 = 119,157.27… → 119,158`, the right end gives `g < 139,265 / 1.10
= 126,604.5… → 126,604`. The 2026-08-15 package sits at `g = 124,177`, **2,427 B below the
top of the window and 5,019 B above the bottom.**

### 9.1 · The build that leaves it, measured first-hand

The wave rebuilds the console **LIVE** — `VITE_MAINLINE_API_BASE=/`, so `source-select.ts`
starts the console on its own kernel instead of a recording — over a source that has also
gained a seventeenth declared resource and a 23,138 B `gate-run.schema.json` imported as
raw text. Built and read on 2026-08-15 on TRAPPOINT, `--console-transport both`,
`MAINLINE_BUILD_ID=3933b97`, zip `sha256
56d6730b8b555f62c8398041f04f0307b3f64fe58626c4e2d1d5d863f30a20c2`; compiled literals read
back out of the packaged bytes as `VITE_MAINLINE_API_BASE=/`,
`VITE_MAINLINE_BUNDLE_URL=./bundle/`, `MODE=demo`, `buildId=3933b97` — i.e. the artefact
this wave is trying to produce, not an approximation of it:

| | deployed (`12fcba7a…`) | LIVE rebuild (`56d6730b…`) | Δ |
|---|---:|---:|---:|
| `web/` entries | 114 | 114 | 0 |
| `web/` bytes | 1,274,743 | 1,308,123 | +33,380 |
| identity objects | 57 / 985,306 | 57 / 1,012,489 | +27,183 |
| `.gz` siblings | 57 / 289,437 | 57 / 295,634 | +6,197 |
| largest identity | `index-DzVoV1YM.js` 433,564 | `index-CwHiUgyV.js` 457,123 | +23,559 |
| **largest sibling — `g`** | **124,177** | **129,404** | **+5,227** |
| `index.html` | 4,655 | 4,655 | 0 |
| identity objects over 139,264 | 1 | 1 | 0 |

### 9.2 · What that does to the ceiling, and what was NOT done about it

```
g = 129,404
1.10 x 129,404                  = 142,344.4  ->  floor 142,344
smallest 8 KiB multiple >= that = 18 x 8,192 = 147,456 = 144 KiB
```

**`147,456 ≠ 139,264`.** `g` is **2,800 B above** the top of the window. Re-recording the
constants from this build would therefore require raising `DEFAULT_MAX_RESPONSE_BYTES` by
one 8 KiB step so that the derivation reproduces it — **raising a ceiling to make a test
pass**, which is precisely the move §5 of this document and the standing no-shortcut rule
forbid, and precisely the move that put this constant at 2 MiB and then at 512 KiB.

So it was not done. **R4 directs the re-recording worker to stop and report to the lead, and
that is what happened.** `test_response_contract.py`, `test_static_site.py` and
`tests/deploy/test_furl_compression.py` all continue to declare the **deployed** package's
numbers, which are true of the artefact on disk and of the tree the Function URL is serving
today. The LIVE package was built to a scratch path and the package at
`out/lambda/mainline-demo-api-arm64.zip` was left untouched, so nothing in the suite is
describing a tree that does not exist.

**One state change that a reader has to know about.** Producing the measurement required
building the console, so `verticals/mainline/apps/console/dist/` now holds the **Phase-2**
tree (`assets/index-CwHiUgyV.js`) rather than the Phase-1 tree the on-disk package was made
from. `dist/` is a gitignored build output and no test reads it as a tree, so nothing is
red because of it — but it means **the next `scripts/deploy/build_lambda.sh
--console-transport both` into the default output path will produce the 129,404 B package
and turn the ratchets in §9.4 red**. That is the intended behaviour of those ratchets and
the reason this section exists; it is not a surprise to route around.

### 9.3 · Two things this is NOT, said explicitly

* **It is not "the ceiling is unsafe".** Interface I3's *bound* still holds on the rebuild:
  `129,404 ≤ 139,264 < 1.20 × 129,404 = 155,284.8`. The origin would still serve its own
  entry chunk to every browser, and would still refuse exactly one object on the identity
  path. What fails is the **tightness** — the property that makes 139,264 a consequence of
  the tree rather than a number somebody liked. That property is the whole content of §5,
  and losing it quietly is worse than losing it loudly.
* **It is not a licence to shrink the test instead.** The alternatives that do not move the
  ceiling all live outside this document: the 23,138 B contract could be code-split out of
  the entry chunk, or the registry could load schemas on demand. Those are console changes,
  owned by the console, and they are the lead's call — **`g` needs to come down by 2,800
  gzipped bytes**, which is roughly half of what the new contract contributes compressed.

### 9.4 · What the next worker inherits

Whoever resolves R4 re-records all three files from the package that resolution produces,
naming that build, and adds a fourth column to §2.2. Until then, a rebuild into
`out/lambda/mainline-demo-api-arm64.zip` turns the following red **at once and by design** —
they are ratchets whose subject moved, not defects:

* `test_static_site.py::test_the_ceiling_is_the_derivation_and_not_a_number_somebody_liked`
  (the derivation equality — the one that names the problem);
* `test_static_site.py::test_the_deployed_package_is_the_tree_the_ceiling_was_derived_from`
  and `…::test_serving_the_deployed_package_derives_the_ceiling_end_to_end`;
* `test_response_contract.py`'s section (c) equalities;
* every case in `tests/deploy/test_furl_compression.py`.

Read those failures. Do not delete, skip, exempt or `continue-on-error` any of them.

> **INHERITED AND DISCHARGED, 2026-08-15 — §10.** The rebuild into
> `out/lambda/mainline-demo-api-arm64.zip` happened and turned all four groups above red,
> exactly as this section predicted. The lead resolved R4 as ruling **R10**; §2.2 now carries
> the fourth column this paragraph asked for, and §10.7 corrects the figures §9.1 measured —
> §9 measured a `--console-transport both` build and what shipped is the `live` one. Nothing
> above is withdrawn.

---

## 10 · RESOLVED — ruling **R10**: 139,264 stands, and the derivation becomes provenance

**Written 2026-08-15 by `w5-decision-record`** on TRAPPOINT, HEAD `3933b97` (working tree
dirty). **Authority:** `docs/leads/reconcile-constants-plan.md` §1, ruling **R10**.
**Artefact of record:** `out/lambda/mainline-demo-api-arm64.zip`,
`sha256 7e49fd5e1426a4d2aaba12a2cd7aa086c95430f0b5daa3645bc8b55eaaed2738`, packed
`--console-transport live`. Every number in this section was read out of that zip by this
worker rather than copied from the plan, with the `zipfile` one-liner §2 publishes.

**§9 stays.** It is not withdrawn, not rewritten and not deleted, and none of its text is
struck. It was correct when it was written and it is the record of a **correct refusal**: a
worker asked to re-record constants found that re-recording them from the build in front of
it would require raising a ceiling, and stopped instead. What has changed is not §9's
reasoning but §9's world — the LIVE package it built to a scratch path is now the package on
disk, and it is a different build from the one §9 measured. §10.7 corrects those figures and
says exactly which ones.

### 10.1 · The STOP is resolved by the lead, exactly as R4 provided for

**R4** of `docs/leads/package-and-verify-plan.md` did not leave the outcome to whoever hit
it: *"If a rebuild puts `g` outside it, **W5 STOPS and reports to the lead**."* W5 stopped
and reported, and §9 is that report. `docs/leads/reconcile-constants-plan.md` §1 is the
lead's answer to it. R10 therefore **closes R4 rather than overruling it** — R4 forbade
*re-deriving the ceiling to fit a bigger bundle*, and no ceiling is re-derived here. The
STOP is discharged, not bypassed, and not "resolved" by the same worker who raised it.

### 10.2 · The ruling

> **`static_site.DEFAULT_MAX_RESPONSE_BYTES` remains `136 * 1024 == 139_264` — unchanged,
> not raised, not lowered.** The live law is interface **I3**, the **straddle**
> `0 < largest_served_gzipped < ceiling < largest_identity_object`, and the property that
> **exactly one** identity object is refused by the ceiling. The derivation
> `ceil(floor(1.10·g)/8192)·8192` is **demoted to dated provenance**: it records how 139,264
> was **chosen**, over the tree it was chosen from — 2026-08-14, package `12fcba7a…`, object
> `assets/index-DzVoV1YM.js.gz`, `g = 124,177` — and it is **no longer asserted against the
> tree that ships**.

Measured here, from the package of record, before anything was concluded from it:

```
g (largest served, gzipped)  =   129,400   web/assets/index-DJX27H0M.js.gz
I (largest identity)         =   457,123   web/assets/index-DJX27H0M.js
                                           sha256 e30bd39b395bad68…
C (ceiling, UNCHANGED)       =   139,264   = 136 * 1024

STRADDLE      0 < 129,400 < 139,264 < 457,123                        HOLDS
I3 lower      129,400 <= 139,264   (the origin serves its own site)  HOLDS
I3 upper      139,264 < 1.20 x 129,400 = 155,280                     HOLDS
EXACTLY ONE   identity objects over 139,264:  1 of 57                HOLDS
              .gz siblings over 139,264:      0 of 57

DERIVATION    floor(1.10 x 129,400)          = 142,340
              ceil(142,340 / 8,192) x 8,192  = 18 x 8,192 = 147,456  != 139,264
```

**Nothing the ceiling exists to do has changed.** The same one object is refused on the
identity path; the same one object is served gzipped; the cost model's multiplier is still
the compressed column. The single sentence that stopped being true is the sentence that *the
formula re-emits the constant* — and that sentence is a claim about the console's size, not
about the ceiling's correctness (§10.4).

### 10.3 · The authority this ruling is made under, named

1. **R5** of `docs/leads/package-and-verify-plan.md` — the derived/authoritative split. It
   enumerated the authoritative side before this incident existed: *"`DEFAULT_MAX_RESPONSE_BYTES
   == 139_264`; **exactly one** identity object refused; `0 < largest_served < ceiling <
   largest_web_object`."* **The derivation FORMULA does not appear on that list.** R10
   applies R5's list; it does not extend it. That is what makes this a ruling rather than an
   invention.
2. **R4** of the same document, which reserved this decision to the lead (§10.1).
3. **R1**, which puts the byte constants and the content-hashed filename in the class
   *measurements of a build*, gated on the build being reproducible. The gate is satisfied,
   measured: `index-DzVoV1YM.js` reproduced 3/3 byte-identical at 433,564 B and
   `index-CmIr4_KY.js` 3/3 at 433,565 B (`evidence/deploy/console-repro.json`, runs
   `committed-phase1` / `committed-phase2`). **One honest caveat travels with that** and is
   recorded in `docs/deploy/console-build.md` §1: those runs build the **committed** console,
   while the shipping package was built from the **worktree** console, so determinism is
   proven and the shipping *filename* is not yet provably reproducible. Per §3 of the lead's
   plan, this section therefore names its artefact by **digest** and not by content hash.
4. **§9.3 of this document**, which conceded the correct framing in the prior worker's own
   words: *"It is not 'the ceiling is unsafe' … What fails is the **tightness**."*
5. **The founder's condition on this deploy: bounds exist in code.** That is what makes
   147,456 unavailable no matter how clean the arithmetic would look.

### 10.4 · The positive argument — a rounded derivation was never a law

`ceil(floor(1.10·g)/8192)·8192` has a **rounding step**, so it is **many-to-one**. It returns
139,264 for *every* `g` in **`[119,158, 126,604]`** — R4's window, re-derived here: the result
is `17 × 8,192` exactly when `floor(1.10·g) ∈ (131,072, 139,264]`, which is `g ≥ 131,073/1.10
→ 119,158` and `g < 139,265/1.10 → 126,604`. That is a **7,447-byte pre-image band**.

So `derive(g) == C` does not say *the ceiling is correct*. It says **`g` is inside that
band** — a statement about **how large the console is permitted to be**. That is a
**bundle-size budget wearing a ceiling's clothes**, and this repository already owns a
bundle-size budget: `verticals/mainline/apps/console/scripts/check-budgets.ts` over
`budgets.json`, whose `evidentiary-shell` entry gates the entry chunk, its static import
closure and its CSS at `max_gzip_bytes: 225280` ("220 KB") and is a test in its own right —
the right instrument for "how big may the console be", and a different question from "how
many bytes may one response carry". Conflating the two is
what generates pressure on the *ceiling* every time the *console* legitimately grows — the
pressure that produced this incident, and that would produce the next one on the next
honest feature.

> **139,264 was CHOSEN by the derivation over the 2026-08-14 tree. It is KEPT by the
> invariant over the 2026-08-15 tree. The number did not move; only the tense of its
> justification did.**

A constant that satisfied a stricter test when it was chosen and satisfies a weaker but
still-binding test today has not been weakened — **because the ceiling itself is
byte-identical**. Nothing that was refused is now served, nothing that was served is now
refused, and nothing that cost X now costs more. A reader who distrusts every word above can
check the only thing that matters in one line: `139_264` in
`verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py`, unchanged, in a file
no worker in this wave was permitted to open.

### 10.5 · The three alternatives, and why each is closed

* **Raise `C` to 147,456 so the formula agrees. FORBIDDEN, under any argument.** It loosens
  a cost bound to satisfy a formula; it is the exact move that put this constant at 2 MiB and
  then at 512 KiB; and it is the move the founder's *bounds exist in code* condition was
  written against. A correct-looking derivation is not a licence — that is what §9 refused,
  and R10 refuses it for the same reason §9 did.
* **Shrink `g` by code-splitting the 23,138 B contract out of the entry chunk** — §9.3's own
  suggestion. This is **changing what ships in order to protect a formula**, after the
  artefact is built, proven in cloud and opened by the founder. Re-deriving the console to fit
  the arithmetic is the same error as re-deriving the arithmetic to fit the console, pointed
  the other way. It is **legitimate future work on its own merits** — a smaller entry chunk is
  a better console, and the four-beat driver would still load — but it is **not this wave's,
  and it is NOT a defect**. Nothing in this repository may record it as one. This supersedes
  §9.3's second bullet as a live instruction; the bullet stays as the record of what was
  considered.
* **Weaken the equality to a bound** (`derive(g) >= C`, or similar). This looks like the
  compromise and is worse than either honest option: it passes for **every** `g` above the
  band, so it refuses nothing. A control that cannot go red is a control in name only, which
  is the precise defect this document's history is made of.

### 10.6 · Two facts that cut against this ruling, said out loud

Recording only the arguments that support a ruling is how a ruling stops being checkable.

* **The I3 ratio moved from 1.121 to 1.076.** The ceiling is *less tight* relative to the
  tree it governs. This is the **safe** direction: `_RATCHET = 1.20` exists to catch the
  ratio **climbing** toward 1.20, where a ceiling floats so far above everything that it
  refuses nothing. Falling toward 1.0 means the bound is biting **harder**, not softer.
* **Headroom fell from 15,087 B to 9,864 B, and that is the number with teeth.** The next
  console growth exceeding **9,864 gzipped bytes** puts `g` above `C`, and the origin then
  **413s its own entry chunk** — a real outage, caught by `_assert_i3`'s lower half.
  **9,864 B of gzipped headroom remain** is the live warning that replaces R4's derivation
  window in every document. No document may carry `119,158 ≤ g ≤ 126,604` as a live
  constraint again; it is provenance now (§2.1).

### 10.7 · §9's figures, CORRECTED — §9 measured a build that did not ship

§9.1 measured a **`--console-transport both`** build: entry chunk `index-CwHiUgyV.js`,
`g = 129,404`, zip `sha256 56d6730b8b555f62…`, built to a scratch path. **That is not what
shipped.** The package of record is **`--console-transport live`**, and it differs from §9's
subject by **four gzipped bytes** on `g` and by a different content hash on the entry chunk.
Read out of the package of record by this worker on 2026-08-15 — the compiled literals
first, because a build's identity is what its bytes carry and not what its command line said:

```
VITE_MAINLINE_API_BASE:"/"        VITE_MAINLINE_BUNDLE_URL:"./bundle/"
VITE_MAINLINE_LOG_VKEY:""         MODE:"demo"        buildId:"3933b97"
web/index.html references assets/index-DJX27H0M.js and assets/index-DAuZRgAW.css
`gate-run` appears 11 times in the entry chunk; `demo_gate_run` twice
```

(`buildId:"unknown"` is also present and is `src/app/honesty.ts`'s EMPTY-record constant, in
every build ever made — `docs/deploy/console-build.md` §7.1 explains why the guard keys on
the presence of `"dev"` and not on there being one literal.)

| | deployed (`12fcba7a…`) | ~~§9.1's `both` build (`56d6730b…`)~~ | **SHIPPED — `live` (`7e49fd5e…`)** | Δ vs deployed |
|---|---:|---:|---:|---:|
| `web/` entries | 114 | 114 | **114** | 0 |
| `web/` bytes | 1,274,743 | 1,308,123 | **1,308,543** | +33,800 |
| identity objects | 57 / 985,306 | 57 / 1,012,489 | **57 / 1,012,812** | +27,506 |
| `.gz` siblings | 57 / 289,437 | 57 / 295,634 | **57 / 295,731** | +6,294 |
| source maps | 0 / 0 | not recorded | **0 / 0** | 0 |
| largest identity | `index-DzVoV1YM.js` 433,564 | `index-CwHiUgyV.js` 457,123 | **`index-DJX27H0M.js` 457,123** | +23,559 |
| **largest sibling — `g`** | **124,177** | **129,404** | **129,400** | **+5,223** |
| 2nd largest identity | `surface-BcxWkbKu.js` 51,266 | not recorded | **`surface-COD-Iou0.js` 51,266** | 0 |
| `index.html` | 4,655 | 4,655 | **4,655** | 0 |
| `index.html.gz` | 2,123 | not recorded | **2,122** | −1 |
| identity objects over 139,264 | 1 | 1 | **1** | 0 |

The `12fcba7a…` column is the reading in §2 of this document, with `index.html.gz` taken from
`docs/leads/reconcile-constants-plan.md` §0.1; that package has been replaced on disk and
cannot be re-read here, which is why its provenance is stated rather than implied. The
`56d6730b…` column is struck as **superseded, not wrong** — it was a true measurement of a
build that was then superseded by the `live` one, and every document that predicted
`g = 129,404` was predicting that build.

**What §9.2's arithmetic becomes.** Substituting the shipped `g`: `floor(1.10 × 129,400) =
142,340`, `ceil(142,340 / 8,192) × 8,192 = 147,456`. The conclusion is **unchanged** —
`147,456 ≠ 139,264`, `g` is above the band, and re-deriving the ceiling from this build would
still be raising a ceiling to make a test pass. §9 was right about that then and R10 is not
disagreeing with it now; R10 answers the question §9 correctly refused to answer alone, and
the answer is that the ceiling does not have to be re-derived at all.

**What §9.2's last paragraph no longer describes.** It records that *"the LIVE package was
built to a scratch path and the package at `out/lambda/mainline-demo-api-arm64.zip` was left
untouched"*. That was true of §9's build. It is **not** true today: the package at that path
is the LIVE one, `sha256 7e49fd5e…`, and `verticals/mainline/apps/console/dist` holds the
matching tree — `dist/assets/index-DJX27H0M.js` is 457,123 B with the same
`sha256 e30bd39b…` as the zip entry.

**What §9.2 predicted, and the one place the prediction was wrong.** §9.2 said the next
default-path build would *"turn the ratchets in §9.4 red"*. It did, and the lead's baseline
in `docs/leads/reconcile-constants-plan.md` §0 records exactly which: **6 cases in
`test_response_contract.py`, 2 in `test_static_site.py`** (`…is_the_tree_the_ceiling_was_derived_from`
and `…derives_the_ceiling_end_to_end`), and **all 30 cases in
`tests/deploy/test_furl_compression.py`**, which error in fixture setup naming the object
that is no longer in the package. **§9.4's first bullet did NOT go red.** The derivation
equality — at HEAD `3933b97` that is `test_static_site.py:876`,
`test_the_ceiling_is_the_derivation_and_not_a_number_somebody_liked`, the case §9.4 called
*"the one that names the problem"* — stayed green, because it derives from the **declared**
`_LARGEST_SERVED_WIRE_BYTES` and not from the tree, and the declaration had not moved yet.

That is worth more than the correction it sits in: **the case expected to name this problem
is the one case that could not see it, and every case that did see it was reading the
artefact.** It is also why §1.6 of the lead's plan splits the input in two. Under R10 that
equality keeps a **frozen** input (`_CEILING_PROVENANCE_G = 124,177`) and therefore stays
green **by design** — it is the guard against the ceiling being silently *re-chosen*, not a
reading of today's tree — while `_assert_i3` takes the re-measured
`_LARGEST_SERVED_WIRE_BYTES = 129,400` and is the case that goes red if this build ever
outgrows the ceiling.

Re-recording the red cases from this package is what ruling R10 authorises and what this wave
does. That is the ratchet working; it is not a defect, and none of those cases may be
deleted, skipped, exempted or given a `continue-on-error`.

### 10.8 · What a later reader must not conclude from this section

* **Not** that measurements may be re-recorded whenever a test is red. They may be
  re-recorded when the artefact they describe has moved and the **invariant still holds**,
  which was checked first and is written out in §10.2.
* **Not** that `DEFAULT_MAX_RESPONSE_BYTES` is now a soft number. It is the one figure in
  this file that no worker in this wave was allowed to open the file of, and the invariant
  that binds it is stricter to state than the derivation was to satisfy.
* **Not** that the derivation is dead code. `_derive_ceiling` and `_assert_i3` stay, with
  their falsification cases; the derivation is asserted against its **frozen provenance
  input** (`g = 124,177`, the value the ceiling was chosen from) so the ceiling can never be
  silently *re-chosen*, while I3 is asserted against **today's** tree. Two constants, two
  assertions, and a reviewer can tell them apart at a glance — the shape is mandated in
  `docs/leads/reconcile-constants-plan.md` §1.6.
