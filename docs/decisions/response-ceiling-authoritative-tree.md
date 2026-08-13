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

```
web/ entries        114 files   1,274,342 B
  identity objects   57 files     985,030 B
  .gz siblings       57 files     289,312 B
  source maps         0 files           0 B

largest identity        433,396 B  assets/index-BjAGxrVJ.js
second-largest identity  51,266 B  assets/surface-Csi7pmRe.js
largest .gz sibling     124,127 B  assets/index-BjAGxrVJ.js.gz

orphan .gz siblings (no identity object):  0
identity objects with no sibling:          0
identity objects over 139,264 B:           1  -> ('assets/index-BjAGxrVJ.js', 433396)
.gz siblings over 139,264 B:               0  -> ()
```

Every figure the lead published reproduces. **Because every identity object has a sibling
and no sibling is an orphan, the bytes a browser pulls are the compressed column
throughout**, so `largest_served_wire_bytes = 124,127` — not 433,396.

### 2.1 · Interface I3, applied

> `largest_served_wire_bytes <= ceiling < 1.20 x largest_served_wire_bytes`, and within that
> window the ceiling is the smallest multiple of 8 KiB at or above
> `1.10 x largest_served_wire_bytes`.

```
1.10 x 124,127                     = 136,539.7
smallest 8 KiB multiple >= that    = 17 x 8,192 = 139,264 = 136 KiB
139,264 / 124,127                  = 1.121948…  -> 1.122, inside the 1.20 ratchet
124,127 <= 139,264                 -> the origin can still serve its own site
```

**`DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024` is a consequence of those three lines, not an
input to them. It does not move.**

### 2.2 · The declarations that follow, and the arithmetic for each

| declaration | was (input tree) | is (deployed tree) | derivation |
|---|---|---|---|
| `_LARGEST_WEB_OBJECT` | `assets/index-BjAGxrVJ.js.map` | `assets/index-BjAGxrVJ.js` | `max(identity)` over the zip |
| `_LARGEST_WEB_OBJECT_BYTES` | 1,554,168 | **433,396** | same |
| `_LARGEST_SERVED_OBJECT_BYTES` | 433,396 | **124,127** | `max(sibling)`; every object has one |
| `_REFUSED_BY_THE_CEILING` | `('…js.map',)` | **`('assets/index-BjAGxrVJ.js',)`** | identity objects `> 139,264` |
| headroom | 90,892 | **15,137** | `139,264 − 124,127` |
| cut | 3.586 | **3.4916** | `433,396 / 124,127` |
| tree totals | `(75, 3,571,990)` | **`(114, 1,274,342)`** | central directory |

Two of these deserve saying out loud.

**The refusal set is not the measured list pasted in.** The input tree's measured refusal
list is `['assets/index-BjAGxrVJ.js', 'assets/index-BjAGxrVJ.js.map',
'assets/surface-CVAkDJuP.js.map', 'assets/surface-Csi7pmRe.js.map',
'assets/worker-BP2nXQVE.js.map']` — five entries, which is what the failing test printed.
The ruling's list is **one** entry. The three maps are gone because the packer strips them,
not because a run happened not to print them. The two lists differ, which is the test that
this is a ruling being implemented rather than an expectation being fitted to output.

**`cut` is 3.4916, not 3.586 and not 3.4917.** The old 3.586 was `1,554,168 / 433,396` — the
source-map strip's cut, a different pair of numbers entirely, and keeping it would have been
comparing a pre-strip artefact to a post-strip one. The new figure is
`433,396 / 124,127 = 3.491553…`, which is **3.4916** to four places. **The lead's §3.4 prose
says 3.4917.** That is a fifth-significant-figure rounding slip in a derived display value,
not a fact about the tree; it does not touch the I3 derivation, the ceiling, or the refusal
set, and the ruling stands. The code asserts the derived value and this paragraph is the
record that the two differ, because silently shipping 3.4916 under a ruling that says 3.4917
is the kind of small unexplained divergence that costs an hour later.

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
* **The declarations are pinned to one build.** `assets/index-BjAGxrVJ.js` is a
  content-hashed name; rebuilding the console changes it and every equality in section (c)
  goes red at once, naming what to re-derive. That is the ratchet working, not a defect —
  but it means these numbers describe the artefact of 2026-08-13 15:54 and nothing later.

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
