<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Reconciling the constants to the artefact that shipped

**Lead:** `constants-lead` · **2026-08-15 on TRAPPOINT** · HEAD `3933b97` (working tree dirty)
· Interpreter `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`
· **Artefact of record:** `out/lambda/mainline-demo-api-arm64.zip`,
`sha256 7e49fd5e1426a4d2aaba12a2cd7aa086c95430f0b5daa3645bc8b55eaaed2738`

This plan does two things and they are not the same size. The small one is arithmetic: eight
demo-api tests and thirty `tests/deploy` errors declare a console build that no longer ships.
The large one is **§1**, a ruling on whether `DEFAULT_MAX_RESPONSE_BYTES` is still the right
number. Nobody edits a constant until §1 is read; §1 is what says which constants are allowed
to move, and it is also what says that one of them is not.

---

## 0 · Baseline, measured here, before anything was decomposed

`.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests -q -p no:randomly
--junitxml=…/baseline.xml` →

```
579 tests · 570 passed · 8 failed · 0 errors · 1 skipped        (161.60 s)
```

The one skip is `test_gate_run.py:1294` (`jsonschema` is not a workspace dependency) and is
pre-existing and unrelated. The eight failures, all one cause:

| # | file | test |
|---|---|---|
| 1 | `test_response_contract.py` | `test_the_ceiling_refuses_something_it_governs` |
| 2 | `test_response_contract.py` | `test_the_largest_file_in_the_built_web_tree_is_the_one_the_ceiling_refuses` |
| 3 | `test_response_contract.py` | `test_the_built_web_tree_has_not_outgrown_its_declaration` |
| 4 | `test_response_contract.py` | `test_every_identity_object_in_the_deployed_tree_serves_or_is_a_declared_refusal` |
| 5 | `test_response_contract.py` | `test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal` |
| 6 | `test_response_contract.py` | `test_the_built_web_tree_matches_the_shape_the_flood_arithmetic_assumed` |
| 7 | `test_static_site.py` | `test_the_deployed_package_is_the_tree_the_ceiling_was_derived_from` |
| 8 | `test_static_site.py` | `test_serving_the_deployed_package_derives_the_ceiling_end_to_end` |

**A ninth thing the brief did not name, and it is the same cause.** `pytest tests/deploy -q`
→ **301 passed, 30 errors**, every error in `tests/deploy/test_furl_compression.py`, failing
in fixture setup with *"the built artefact no longer matches the sizes this file declares …
`{'/assets/index-DzVoV1YM.js': -1, …}`"*. `-1` is that file's own word for *the declared
object is not in the package at all*. Ruling **R9** of `docs/leads/package-and-verify-plan.md`
and §9.4 of `docs/decisions/response-ceiling-authoritative-tree.md` both name this file as
part of this cause and both forbid deleting, skipping or exempting it. It is in scope. **The
target is 579/578/0/0/1 on demo-api and 331/331/0/0 on `tests/deploy`.**

## 0.1 · The artefact, read from its own central directory

Read by this lead from the zip, not copied from any document:

| | deployed **before** (`12fcba7a…`) | **shipping now** (`7e49fd5e…`) | Δ |
|---|---:|---:|---:|
| `web/` entries | 114 | **114** | 0 |
| `web/` bytes | 1,274,743 | **1,308,543** | +33,800 |
| identity objects | 57 / 985,306 | **57 / 1,012,812** | +27,506 |
| `.gz` siblings | 57 / 289,437 | **57 / 295,731** | +6,294 |
| source maps | 0 / 0 | **0 / 0** | 0 |
| largest identity | `index-DzVoV1YM.js` 433,564 | **`index-DJX27H0M.js` 457,123** | +23,559 |
| **largest sibling — `g`** | **124,177** | **129,400** | **+5,223** |
| 2nd largest identity | `surface-BcxWkbKu.js` 51,266 | **`surface-COD-Iou0.js` 51,266** | 0 |
| `index.html` | 4,655 | **4,655** | 0 |
| `index.html.gz` | 2,123 | **2,122** | −1 |
| identity objects over the ceiling | 1 | **1** | 0 |

Entry chunk `sha256 e30bd39b395bad68…`, and `verticals/mainline/apps/console/dist/assets/index-DJX27H0M.js`
is 457,123 B with the same digest — `dist` and the zip agree, as the brief states. **Do not
disturb `dist`.**

**Two facts about neighbours, recorded so nobody "fixes" them.**

* `out/lambda/mainline-demo-api-x86_64.zip` is **stale** — it still carries
  `index-BjAGxrVJ.js` at 433,396 B, a console two builds old. No test reads it: both
  `_PACKAGE` constants point at the arm64 zip, and arm64 is what deployed. **Nobody rebuilds
  it in this wave.** Rebuilding is a build action with no test asking for it, and the
  prohibition on touching the deployed path outweighs the tidiness.
* The prior record in `docs/decisions/…§9` describes a `--console-transport both` build
  (`index-CwHiUgyV.js`, `g = 129,404`, zip `56d6730b…`). **That is not what shipped.** The
  shipping package is `--console-transport live`: same identity size, **`g = 129,400`**, four
  bytes apart. Every document that predicted `129,404` — `COST-BOUND.md:26` does — is
  predicting a build that was superseded. Re-record `129,400`, and say which build.

---

## 1 · RULING R10 — the ceiling stands at 139,264, and the derivation is demoted to provenance

> **`static_site.DEFAULT_MAX_RESPONSE_BYTES` remains `136 * 1024 == 139_264`, unchanged, not
> raised, not lowered. The live law is interface I3 and the straddle. The derivation
> `ceil(floor(1.10·g)/8192)·8192` is preserved as a dated record of how 139,264 was CHOSEN,
> over the tree it was chosen from, and is no longer asserted against the current tree.**

This is answer **(a)** of the two the brief offered. I considered (b) and rejected the
candidates; §1.3 says why. The reasoning below is the thing workers are bound by.

### 1.1 · The authority I am acting under

1. **R5** of `docs/leads/package-and-verify-plan.md` — the derived/authoritative split. It
   already enumerates the authoritative side: *"`DEFAULT_MAX_RESPONSE_BYTES == 139_264`;
   **exactly one** identity object refused; `0 < largest_served < ceiling <
   largest_web_object`."* **The derivation formula is not on that list.** R5 is what makes
   this ruling available rather than inventive: it decided, before this incident, which facts
   are the law. I am applying its list, not extending it.
2. **R4** of the same document reserved this decision explicitly — *"If a rebuild puts `g`
   outside it, **W5 STOPS and reports to the lead**"*. W5 stopped and reported; the report is
   `docs/decisions/response-ceiling-authoritative-tree.md` §9, and it is a good one. **This
   section is the lead resolution R4 was waiting for**, and it closes R4 rather than
   overruling it: R4 forbade *re-deriving the ceiling to fit a bigger bundle*, and no ceiling
   is being re-derived here.
3. **R1** as restated in my brief — the byte constants and the content-hashed filename are
   measurements of a build, gated on the build being reproducible. That gate is satisfied:
   `index-DzVoV1YM.js` reproduced 3/3 byte-identical at 433,564 and `index-CmIr4_KY.js` 3/3 at
   433,565 (`evidence/deploy/console-repro.json`). §5 records the one honest caveat on that.
4. **§9.3 of the decision record**, which already conceded the correct framing in the prior
   worker's own words: *"It is not 'the ceiling is unsafe' … What fails is the **tightness**."*
5. The founder's condition, restated in my brief: **bounds exist in code**. That is what makes
   147,456 unavailable regardless of how clean the arithmetic would look.

### 1.2 · The measurement the ruling rests on

Every one of these was computed by this lead from the shipping zip:

```
g (largest served, gzipped)  = 129,400
I (largest identity)         = 457,123
C (ceiling, UNCHANGED)       = 139,264

STRADDLE      0 < 129,400 < 139,264 < 457,123                      HOLDS
I3 lower      129,400 <= 139,264       (origin serves its own site) HOLDS
I3 upper      139,264 < 1.20 x 129,400 = 155,280                    HOLDS
EXACTLY ONE   identity objects over 139,264: 1 of 57                HOLDS

DERIVATION    floor(1.10 x 129,400) = 142,340
              ceil(142,340 / 8,192) x 8,192 = 18 x 8,192 = 147,456  != 139,264
```

**Nothing that the ceiling was for has changed.** The same one object is refused on the
identity path; the same one object is served gzipped; the cost model's multiplier is still
the compressed column. The only statement that stopped being true is the statement that the
formula re-emits the constant.

### 1.3 · Why the three alternatives are not available

* **Raise C to 147,456 so the formula agrees.** Forbidden outright — it loosens a cost bound
  to satisfy a formula, and it is the exact move that put this constant at 2 MiB and then at
  512 KiB. It is also the move the founder's deploy condition was written against. Not
  available under any argument, including a correct-looking one.
* **Shrink `g` by code-splitting the 23,138 B contract out of the entry chunk** (§9.3's own
  suggestion). This would restore the derivation — and it means **changing what ships in order
  to protect a formula**, after the artefact is deployed, proven in cloud, and opened by the
  founder. Re-deriving the console to fit the arithmetic is the same error as re-deriving the
  arithmetic to fit the console, pointed the other way. It is legitimate *future* work on its
  own merits (a smaller entry chunk is a better console); it is not this wave's, and it must
  not be recorded as a defect.
* **Assert the derivation as a bound rather than an equality** (e.g. `derive(g) >= C`). This
  looks like a compromise and is worse than either honest option: it is an assertion that
  passes for every `g` above the window and therefore refuses nothing — a control in name
  only, which is the precise defect this file's history is made of.

### 1.4 · The positive argument — why a rounded derivation was never a law

A derivation with a **rounding step is many-to-one**. `ceil(floor(1.10·g)/8192)·8192` returns
139,264 for *every* `g` in `[119,158, 126,604]` (R4's window, re-derived and agreed). So the
assertion `derive(g) == C` does not say *the ceiling is correct*; it says **`g` is inside a
particular 7,447-byte pre-image band** — which is a statement about how large the console is
permitted to be. That is a **bundle-size budget wearing a ceiling's clothes.** This repository
already owns a bundle-size budget (`verticals/mainline/apps/console/scripts/check-budgets.ts`).
Conflating the two is precisely what generates pressure on the ceiling every time the console
legitimately grows — the pressure that produced this incident and will produce the next one.

What the ceiling must actually guarantee is I3 plus the straddle plus exactly-one-refusal, and
all three are measured true. So:

> **139,264 was CHOSEN by the derivation over the 2026-08-14 tree. It is KEPT by the invariant
> over the 2026-08-15 tree. The number did not move; only the tense of its justification did.**

A constant that satisfied a stricter test when chosen and satisfies a weaker but still-binding
test today has not been weakened, **because the ceiling itself is byte-identical**: nothing
that was refused is now served, and nothing that cost X now costs more.

### 1.5 · The two things this ruling requires to be said out loud, because they cut against it

* **The ratio moved from 1.121 to 1.076.** The ceiling is *less tight* relative to the tree.
  That is the **safe** direction: the danger the `_RATCHET = 1.20` guard exists for is the
  ratio climbing toward 1.20, where a ceiling floats so far above everything that it refuses
  nothing. Falling toward 1.0 means the bound is biting harder, not softer.
* **Headroom fell from 15,087 B to 9,864 B**, and *that* is the number with teeth. The next
  console growth exceeding **9,864 gzipped bytes** puts `g` above `C` and the origin 413s its
  own entry chunk — a real outage, caught by `_assert_i3`'s lower half. **This is the live
  warning that replaces R4's derivation window in every document.** Docs must carry `9,864 B
  of gzipped headroom remain` and must not carry `119,158 <= g <= 126,604` as a live
  constraint.

### 1.6 · The shape the ruling MANDATES in code — non-negotiable, W1 owns it

Two constants, two roles, impossible to confuse at a glance:

```python
#: FROZEN HISTORY. The gzipped measurement 139,264 was CHOSEN from, 2026-08-14, package
#: sha256 12fcba7a…, object assets/index-DzVoV1YM.js.gz. This number is NOT a measurement
#: of the tree that ships and MUST NEVER BE RE-MEASURED. It moves only if the ceiling is
#: deliberately re-chosen, which is a decision, not a re-record. (Ruling R10 §1.6.)
_CEILING_PROVENANCE_G: Final = 124_177

#: RE-MEASURED per build. The largest number of bytes this origin puts on the wire for one
#: response, from the package that ships today. Interface I3's live input.
_LARGEST_SERVED_WIRE_BYTES: Final = 129_400   # web/assets/index-DJX27H0M.js.gz
```

and correspondingly two assertions that can never be mistaken for each other:

* `_derive_ceiling(_CEILING_PROVENANCE_G) == 139_264 == 136 * 1024` — **provenance**: the
  ceiling still equals what its derivation produced, so it can never be silently *re-chosen*.
* `_assert_i3(static_site.DEFAULT_MAX_RESPONSE_BYTES, _LARGEST_SERVED_WIRE_BYTES)` —
  **the live law**, against today's tree.

`_derive_ceiling` and `_assert_i3` are **not deleted, not weakened, and not made conditional.**
The falsification parametrisation stays and keeps falsifying.

---

## 2 · The rule every worker applies to every number they touch

For each constant, answer in the comment beside it, in this order:

1. **what it was** and **what it is**;
2. **which build produced the new value** — name `out/lambda/mainline-demo-api-arm64.zip`,
   `sha256 7e49fd5e…`, `--console-transport live`, `MAINLINE_BUILD_ID=3933b97`;
3. **why it is a measurement and not a floor** — the R1/R5 sentence, in your own words, for
   *this* constant.

A reviewer must be able to tell measurement from bound **instantly**. Therefore:

* **MAY MOVE (measurements of a build):** `_LARGEST_WEB_OBJECT(_BYTES)`,
  `_LARGEST_SERVED_OBJECT(_BYTES)`, `_LARGEST_SERVED_CODING`, `_LARGEST_SERVED_WIRE_BYTES`,
  `_LARGEST_IDENTITY_BYTES`, `_SECOND_LARGEST_IDENTITY_BYTES`, `_WIDEST_SERVED_IDENTITY(_BYTES)`,
  `_REFUSED_BY_THE_CEILING`, `_WEB_TREE_BYTES`, `_IDENTITY_BYTES`, `_SIBLING_BYTES`, the
  derived `headroom` / `ratio` / `cut` / falsification-pin figures, and the doc tables.
* **MUST NOT MOVE (bounds):** `static_site.DEFAULT_MAX_RESPONSE_BYTES` (139,264 — **no worker
  opens `static_site.py` at all**), `_HEADROOM = 1.10`, `_ROUNDING = 8*1024`,
  `_RATCHET = 1.20`, `_CEILING_PROVENANCE_G` (new, frozen), the straddle invariant, the
  exactly-one-refusal property, `_WEB_TREE_ENTRIES = 114`, `_IDENTITY_OBJECTS = 57`,
  `_WEB_ENTRIES = 114`, `_IDENTITY_ENTRIES = 57` (these four are unchanged **by measurement**
  — assert them, do not touch them).

### The derived figures, computed once here so five workers cannot disagree

```
headroom           139,264 - 129,400 = 9,864          (was 15,087)
I3 ratio           139,264 / 129,400 = 1.0762…  → 1.076  (was 1.121)
compression cut    457,123 / 129,400 = 3.53263… → 3.5326 (was 3.4915)
1.10 x g           142,340.0                          (was 136,594.7)
falsification pin  smallest int >= 1.20 x 129,400 = 155,280  (was 149,013)
```

The falsification pin at `155_280` **rises**; that is the case doing its job, and the file's
own comment pre-authorises it: *"Leaving it at 149,000 after the tree grew … would have made
THIS case stop raising, which is the loud failure the pin is for."* Raising it is not raising
a ceiling — it is following the ratchet the tree moved.

---

## 3 · Wording that will not go stale the next time the console grows

Documents keep breaking because they hard-code a build's identity into a sentence about a
property. Prefer, everywhere:

* **name the artefact by digest, and date the measurement** — "measured 2026-08-15 on
  `arm64.zip sha256 7e49fd5e…`", never "the current build";
* **state the property, then the measurement** — "the ceiling refuses exactly one identity
  object; today that object is `assets/index-DJX27H0M.js` at 457,123 B", never "the ceiling
  refuses `index-DJX27H0M.js`";
* **carry the headroom, not the window** — "9,864 gzipped bytes of headroom remain before the
  origin would 413 its own entry chunk", never R4's `119,158 <= g <= 126,604` as a live rule;
* **never write "the latest build" or "today's package"** without a digest beside it.

---

## 4 · Decomposition — five workers, disjoint literally-enumerated paths

No two workers may open the same file. **Nobody opens
`verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py`.** Nobody commits.

| worker | owns, literally |
|---|---|
| **W1 · the ceiling's own file** | `verticals/mainline/apps/demo-api/tests/test_static_site.py` |
| **W2 · the response contract** | `verticals/mainline/apps/demo-api/tests/test_response_contract.py` |
| **W3 · the deploy suite** | `tests/deploy/test_furl_compression.py`, `tests/deploy/test_docs_are_true.py` |
| **W4 · the cost and latency pages** | `docs/deploy/COST-BOUND.md`, `docs/deploy/LATENCY.md`, `docs/ci/cluster-lane-package.md` |
| **W5 · the record and the ruling** | `docs/decisions/response-ceiling-authoritative-tree.md`, `docs/deploy/console-build.md` |

W1 and W2 are independent (different files, same measurements — both take them from §0.1 and
§2 of this plan, not from each other). W3 may start immediately; its `test_docs_are_true.py`
run is meaningful only after W4 and W5 land, so W3 re-runs it at the end. W4 and W5 are
independent of the test workers and of each other.

Every brief repeats, verbatim: **no `terraform apply`, no redeploy, no AWS, no SSM write, no
DSN printed; no raising `DEFAULT_MAX_RESPONSE_BYTES`, no lowering a floor, no raising a skip
ceiling, no `continue-on-error`, no `|| true`, no known-red exemption, no `pytest.skip` or
`xfail` added; do not run `console_repro.py` against the worktree console; do not touch
`verticals/mainline/apps/console/dist`; do not run `ruff format` across the repo; do not
commit.**

---

## 5 · The tree_digest discrepancy — NOT settled, handed on, with the evidence and the caveat

**The discrepancy.** `docs/deploy/console-build.md:143-144` quotes tree digests `89042d19…`
(Phase 1) and `53cd5a97…` (Phase 2). `evidence/deploy/console-repro.json` today holds
`bf3ec22e…` and `857ce28b…` for the same two labels — while **every entry-chunk figure agrees**
(`index-DzVoV1YM.js` 433,564 / `index-CmIr4_KY.js` 433,565, each 3/3 byte-identical).

**What I established, first-hand:**

1. `tree_digest` is `rollup_digest(tree_digests(dist))` — `sha256` over
   `name\0size\0sha256\n` for **every file the build emitted**, 49 files per run: the entry
   chunk, 18 `.js.map` files, the CSS, and `.vite/manifest.json`
   (`scripts/deploy/console_repro.py:148-176, 421-426`). It is therefore **much wider than the
   entry chunk**, and the entry chunk agreeing tells us nothing about it.
2. Chunk *names* are content hashes, so a differing chunk would rename itself and the names do
   not differ. The files that can change bytes **without** changing any name are the `.map`s
   (their names derive from the chunk, their bytes include `sourcesContent`, i.e. the source
   text verbatim) and `.vite/manifest.json` (names only, so it would not differ).
3. `.map` `sources` entries are **relative** (`../../src/design/primitives/ConstraintName.tsx`)
   and `sourceRoot` is absent, so the scratch export path does **not** leak into a map. The
   "different temp directory" explanation is **ruled out**.
4. `evidence/deploy/console-repro.json` is **untracked** — `git log -- ` it and `git show
   HEAD:` it both come back empty. **Git holds no earlier version.** The per-asset record of
   the run that produced `89042d19…` was overwritten in place and exists nowhere in the tree
   or its history.

**Therefore I do not settle it, and I will not invent an explanation.** The plausible
mechanism — that the `89042d19…` run's inputs carried CRLF where the `git archive` export
carries LF, changing `sourcesContent` in all 18 maps while leaving the emitted JS identical —
is *consistent* with the recorded `"i/lf w/crlf": 31` EOL census and with this tree's already
documented CRLF-changes-the-bundle behaviour, **but it is a hypothesis and it is not
supported by any artefact.** Saying it as fact would be exactly the failure this wave exists
to correct.

**What would settle it, named:** the per-asset `{name, bytes, sha256}` map of the run that
produced `89042d19…`, diffed against the recorded run's. If only `.map` files differ, the
mechanism is source-text; if a `.js` differs, the build is not deterministic and that is a
larger finding than any number here. Since that record no longer exists, the substitute is:
re-run `console_repro.py --builds 1 --source rev:HEAD --out <scratch>/probe.json` (**`--out`
to a scratch path; `--source rev:HEAD` exports with `git archive`, never touching the worktree
console or `dist`**) to confirm `bf3ec22e…` is stable for the committed source, then re-run
under the suspected earlier input to see whether `89042d19…` reappears.

**W5's remedy — make the document true without asserting a cause.** Replace the two quoted
digests with the values `evidence/deploy/console-repro.json` actually holds (`bf3ec22e…`,
`857ce28b…`), naming the run and its `measured_at`, and add a short dated note recording that
two earlier digests were quoted for the same builds, that the record behind them was
overwritten and is not in git, that the entry chunks agree, and what would settle it. **Do not
present `bf3ec22e…` as the same measurement re-expressed — it is a different invocation.**

### 5.1 · A caveat on R1's gate that must travel with this wave

`console_repro.py --source rev:HEAD` builds the **committed** console and emits 433,564 /
433,565 B. The package that ships was built from the **worktree** console, which is genuinely
different: `git diff --stat HEAD -- verticals/mainline/apps/console` is *14 files changed,
1,689 insertions*, and `src/data/contracts.ts:49` imports
`'../../contracts/gate-run.schema.json?raw'` in the worktree while `git grep` at HEAD finds no
such import. That import is the +23,559 B. Consequently:

* **What is proven:** the console build is *deterministic* — same source, same bytes, 3/3, at
  two different sources. That is what R1's gate asked and it is satisfied.
* **What is NOT proven:** that the shipping filename `index-DJX27H0M.js` is reproducible,
  because the source it was built from is not committed. It becomes provable the moment the
  orchestrator commits the console work.
* `console-repro.json`'s `"worktree_matches_committed": true` was measured at
  `2026-08-15T02:44:52+1000`, **before** that console work reached the worktree, and is now
  stale in that respect. W5 records this; **W5 does not regenerate the file** (regenerating it
  is a build, and the safe form of that build is the `--out`-to-scratch probe above).

This does not block the re-record. R1 gates the *class* of constant on build determinism, and
determinism is measured. It does mean the re-record must name the artefact by **digest**, per
§3, rather than resting on a content hash whose source is not yet in git.

---

## 6 · Done

Demo-api **579 / 578 passed / 0 failed / 0 errors / 1 skipped**; `tests/deploy` **331 / 331 /
0 errors**; `git diff` shows `static_site.py` untouched and `139_264` unchanged everywhere;
every moved number carries its what-it-was / which-build / why-a-measurement comment; no skip,
xfail, exemption or `continue-on-error` added anywhere.
