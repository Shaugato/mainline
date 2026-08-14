<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PACKAGE AND VERIFY — the lead's plan

**Lead:** package-and-verify. **Written:** 2026-08-14. **Workers:** 6, paths disjoint and
literally enumerated in §7.

Every number below was measured by this lead in this session. Nothing is quoted from a
brief without re-measuring it, and where a re-measurement contradicts the brief that is
said in the open (§2.4, §3.3).

---

## 0. THE ONE SENTENCE

The console that is deployed right now is a **REPLAY** artefact whose headline beat is
**not addressable**, every local test passed over it, and the founder found it — so the
work is to put the checks on the **packaged bytes**, rebuild the artefact so the checks
pass honestly, and leave behind an executable that a judge's walk can be re-run from.

---

## 1. BASELINE — measured, not assumed

### 1.1 The live deployment, fetched by this lead

    GET  https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/
         -> 200, 4,655 B, 0.700 s
    GET  .../v1/health
         -> 503  {"ok": false, "reason": "dsn_unset", ...}
         detail: SSM GetParameter '/mainline/demo/cockroach_dsn' in ap-southeast-1
                 answered HTTP 400: {"__type":"ParameterNotFound"}

The served `index.html` is **4,655 B** and references `./assets/index-DzVoV1YM.js` and
`./assets/index-C498vmEA.css`. The local package `out/lambda/mainline-demo-api-arm64.zip`
carries `web/index.html` at **exactly 4,655 B** and `web/assets/index-DzVoV1YM.js`. **The
package on disk is the tree that is serving.** That identity is what makes every
artefact-level assertion in this plan meaningful rather than hypothetical.

`POST /v1/demo/gate-run` was **not** re-driven by this lead; the orchestrator's measurement
(503, `kind="dsn_unset"`) stands and is consistent with `/v1/health` above. The route
exists — a 503 with a named cause is not a 404.

### 1.2 The demo-api suite, run twice with `--crdb=reuse`

Command (the only interpreter that runs this suite; `uv` is not on PATH):

    .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api \
      --crdb=reuse -q -p no:randomly --junitxml=<path>

| run | junitxml `tests/failures/errors/skipped` | passed | terminal summary | wall |
|---|---|---|---|---|
| 1 | 576 / 0 / 0 / 1 | 575 | **`1 failed, 574 passed, 1 skipped`** | 184.18 s |
| 2 | 576 / 0 / 0 / 1 | 575 | `575 passed, 1 skipped` (exit 0) | 151.57 s |

**Run 2 reproduces the declared baseline exactly: 576 / 575 / 0 / 0, one skip.** The single
skip is `test_gate_run.py::test_payload_validates_against_the_json_schema` —
*"jsonschema is not a workspace dependency"* — which is a declared, self-describing skip and
is not touched by anything in this plan.

**Run 1 did not, and the disagreement is unresolved.** Its terminal reported

    FAILED verticals/mainline/apps/demo-api/tests/test_transitions.py::test_a_run_that_really_persists_is_caught
    psycopg.errors.SerializationFailure: restart transaction:
      TransactionRetryError: retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)

while **its own `--junitxml` recorded that test as passed, with zero `<failure>` elements in
the whole document**. I could not reconcile the two from the artefacts available, and I am
not going to pretend the run was clean because the second one was. Two readings exist:

* **Benign:** `test_a_run_that_really_persists_is_caught` is genuinely flaky under
  `--crdb=reuse` (a 40001 against a reused cluster is exactly the contention this repository
  goes out of its way to provoke), and the XML/terminal mismatch is a reporting artefact.
* **Not benign:** something in the lane records a failure as a pass in the JUnit document.
  That is *laundering*, it is the same shape as the defeater this project exists to catch,
  and it would make every `--junitxml` number in every worker report — including the
  baseline this plan is built on — worth nothing.

This is why **R11** (§5) binds every worker: report the junitxml numbers *and* the terminal
summary, every time, and treat any disagreement between them as a STOP.

### 1.3 The packaged web tree, read from the zip's central directory

    entries in web/                      114
    web/ total bytes                     1,274,743
    largest identity object              web/assets/index-DzVoV1YM.js         433,564 B
    largest gzipped sibling              web/assets/index-DzVoV1YM.js.gz      124,177 B
    identity objects over the ceiling    exactly 1  -> assets/index-DzVoV1YM.js
    web/index.html                       4,655 B

Cross-checked against `verticals/mainline/apps/demo-api/tests/test_response_contract.py`
(`_WEB_TREE_ENTRIES=114`, `_WEB_TREE_BYTES=1_274_743`, `_LARGEST_WEB_OBJECT_BYTES=433_564`,
`_LARGEST_SERVED_OBJECT_BYTES=124_177`, `_REFUSED_BY_THE_CEILING=('assets/index-DzVoV1YM.js',)`)
and `test_static_site.py` (`_LARGEST_SERVED_WIRE_BYTES=124_177`,
`_LARGEST_IDENTITY_BYTES=433_564`). **They agree, today, exactly.** Scope (d) currently
HOLDS — and it holds against the tree that is deployed. Any console rebuild moves all of it.

### 1.4 The compiled mode, read out of the deployed bytes

`grep` over `web/assets/index-DzVoV1YM.js` inside the package, and over the identical file
in `console/dist`:

    VITE_MAINLINE_API_BASE:""            <- empty  => source-select.ts trims it to null
    VITE_MAINLINE_BUNDLE_URL:"./bundle/" <- set    => REPLAY
    VITE_MAINLINE_LOG_VKEY:""
    MODE:"demo"

`out/lambda/mainline-demo-api-arm64.zip.json`, written by the packer itself, records the
same three keys. **FAULT 1 is confirmed in the shipped bytes, not inferred from source.**

---

## 2. WHAT IS WRONG, PRECISELY

### 2.1 FAULT 1 — the artefact is REPLAY

`src/app/source-select.ts:104-108,124-125` trims each variable and treats `""` as unset.
`.env.demo` sets `VITE_MAINLINE_BUNDLE_URL=./bundle/` and leaves `VITE_MAINLINE_API_BASE=`
**deliberately empty**, and says so in its own header:

> *"the file committed here builds the demo that CANNOT FAIL … Phase 2 adds the live API by
> supplying the variable in the ENVIRONMENT, which Vite applies after every .env file, so no
> committed file is edited by a deploy:* `VITE_MAINLINE_API_BASE=/ pnpm exec vite build --mode demo`*"*

So the committed default is Phase 1 by design, and the deploy that produced the live
artefact **ran the Phase-1 command**. The defect is a missing build input, not a bug in the
selector. `scripts/deploy/build_lambda.sh:313` runs the bare
`pnpm exec vite build --mode demo`, i.e. Phase 1, and nothing downstream objects.

### 2.2 FAULT 1b — the guard that should have objected cannot fire

`build_lambda.sh:618-656` (`probe_console`) collects every `VITE_MAINLINE_*:"…"` literal it
finds in `web/assets/*.js`. Line 875 then reads:

    if console["configured"]:            # -> print the pairs
    else:                                # -> the WARNING

`VITE_MAINLINE_LOG_VKEY` is compiled into every build. So `configured` is **never empty**,
so the warning branch is **unreachable in practice** — and it did not fire for the artefact
that reached the founder. Worse, the probe records `VITE_MAINLINE_API_BASE: ""` as
*carried*, while `source-select.ts` treats the same value as *absent*. Two places hold one
fact and they disagree — which is the exact failure mode `source-select.ts`'s own docstring
names about badges (*"the day they disagree is the day the badge is decoration"*).

This is the single most important finding in this plan, because it is the mechanism by which
a packaged defect walked past a guard that was written to catch it.

### 2.3 FAULT 2 — the headline beat is not addressable

`resources.ts` declares 16 resources; `demo_gate_run` is not one of them.
`DemoDriver.tsx:252-276` therefore renders *"POST /v1/demo/gate-run is not addressable from
this console"* and refuses to use a bare `fetch`, correctly: that would skip envelope and
contract validation and would have no REPLAY counterpart (D7).

### 2.4 FAULT 2's banner carries one false line — corrected here

`DemoDriver.tsx:84-87` (`DECLARATION_GAP[2]`) says of `app.py`:

> *"the route table declares the four kernel POSTs and no demo route, so the endpoint 404s."*

**That is false today.** `app.py:229` contains
`Route("POST", "/v1/demo/gate-run", "demo_gate_run")`, `app.py:188-206` describes it as *the
seventeenth*, `tests/test_routes_gate_run.py` pins it, and the live URL answers **503
`dsn_unset`** — a reachable route refusing for a named reason. The prose is stale, and prose
that tells a reader to go and fix something already fixed is a defect of the same family as
the one that shipped. **W3 corrects it.**

### 2.5 An undeclared RED nobody listed — found by this lead

    .venv/Scripts/python.exe -m pytest tests/deploy/test_furl_compression.py --crdb=none -q
    -> 30 errors in 2.79 s

    FileNotFoundError: ...\furl-web0\web\assets\index-BjAGxrVJ.js

`tests/deploy/test_furl_compression.py:77-79,162-163` pins the **previous** console identity
— `assets/index-BjAGxrVJ.js`, 433,396 B identity, 124,127 B gzipped, and 57 siblings of
289,312 B — and it **unpacks the real artefact** to check them. The artefact carries
`index-DzVoV1YM.js`, 433,564 / 124,177, siblings 289,437 B. Every one of its 30 tests errors
in fixture setup.

It appears in **neither** `docs/CI-STATE.md` nor `docs/HONESTY.md`, and **no workflow runs
`tests/deploy` at all** (`grep` over `.github/workflows/`: zero hits). So the repository
contains an artefact-level test suite, aimed squarely at the class of defect that reached
the founder, that is red on disk and invisible to CI. That is the brief's thesis stated as a
fact about this tree.

---

## 3. RULINGS — where the brief is open, with the authority named

**R1 — FAULT 2's console-source remedy is IN SCOPE.** *Authority:* my scope (c) requires the
judge walk to *"drive every declared resource, drive the gate-run beat"*; a beat that is not
declared cannot be driven by a console-faithful walk, so (c) is unreachable without it. Also
the ratified tiebreaker: *the console and the committed JSON schemas are authoritative for
what the demo must carry.* Declaring the resource makes the console the authority; it does
not move a floor. **Assigned to W3.**

**R2 — the shipped artefact carries BOTH sources, built with `VITE_MAINLINE_API_BASE=/`.**
Not "replace REPLAY with LIVE". *Authority:* `source-select.ts:16-18` — *both set → LIVE,
with a control that can switch to REPLAY* — and `.env.demo`'s own Phase-2 line, verbatim,
which prescribes `/` (not a hostname) because the console and the API share one origin. This
gives the founder's complaint its fix (the badge reads LIVE, the console talks to its own
kernel) while keeping the "cannot fail" property one control away, which is a *better* demo
beat than either alone. **`.env.demo`'s committed value is NOT edited to hardcode the API
base** — the file states that a deploy must not edit a committed file, and the build command
is the deploy's input. **W1 owns the change to how the build is invoked; W2 owns the guard
that refuses a package built the old way.**

**R3 — reproducibility is measured before anything is re-recorded.** A content-hashed
filename is a legitimate constant only if the build is reproducible. The tree records **two
distinct content hashes at an identical byte length**: `index-BKZMI9SJ.js` at 433,564
(`docs/ci/cluster-lane-package.md` §4, "the fresh build at HEAD") and `index-DzVoV1YM.js` at
433,564 (the tests, the package, and the live URL). Same length, different content is *not*
explained by the `define` defaults (`'dev'`=3, `'unknown'`=7, `'absent'`=6,
`'g1-attestation.json'`=19 characters — all different lengths). And I measured that
`evidence/attestations/g1-attestation.json` and `evidence/g1-attestation.json` **do not
exist**, so `vite.config.ts:32-63` resolves `unknown`/`absent` today. Therefore either one of
those two records is mislabelled or the build varies by a same-length value, and **neither is
assumed**: W1 builds N≥3 times from a clean tree and hashes every emitted asset. *"if it is
not [reproducible], that is a LARGER finding than the numbers and the fix is to remove the
nondeterminism, never to re-record a hash you cannot re-measure"* — my brief, verbatim, and
it governs.

**R4 — the ceiling may not move, and I have derived the window that keeps it fixed.**
`DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024 == 139_264` is authoritative. From
`test_static_site._derive_ceiling` — `ceil(floor(1.10·g) / 8192) · 8192` — and `_assert_i3`
(`g ≤ ceiling < 1.20·g`), I computed by exhaustive search that the derivation yields exactly
139,264 for

    119,158  <=  g  <=  126,604        (g = gzipped bytes of the largest served object)

Today `g = 124,177`: **upward headroom 2,427 gzipped bytes, downward slack 5,019.** A console
that gains a 17th resource, a 17th schema and a live transport must land inside that window.
If a rebuild puts `g` outside it, **W5 STOPS and reports to the lead**; re-deriving the
ceiling to fit a bigger bundle is raising a ceiling to pass a test and is forbidden.

**R5 — derived vs authoritative, restated for this wave.** The content hash and the four byte
constants are the DERIVED side and may be re-recorded, **naming the build that produced
them** (`docs/ci/cluster-lane-package.md` R5). The AUTHORITATIVE side, which may not move to
make a re-record fit: `DEFAULT_MAX_RESPONSE_BYTES == 139_264`; **exactly one** identity object
refused; `0 < largest_served < ceiling < largest_web_object`. *Ask which side is
authoritative, never which is easier to move.*

**R6 — the assertion goes on the packaged `web/` tree.** Specifically on the `web/` entries of
`out/lambda/mainline-demo-api-*.zip`, not on `console/dist` and not on source. *Authority:*
my brief (*"the defect that reached the founder was a packaged artefact"*), and
`test_response_contract.py:880-882` which already rules that *"the packer's input tree is
deliberately NOT accepted as a stand-in"*.

**R7 — `probe_console` must apply the console's own rule, and the guard must REFUSE.** The
probe adopts `source-select.ts`'s `trimmed()` semantics (`""` and whitespace are *unset*), and
`build_lambda` **refuses** — not warns — to emit a package whose `web/` tree carries no LIVE
source. An `--allow-replay` flag exists so a deliberate Phase-1 package is still buildable,
and it must be typed on the command line: the opt-out is a sentence somebody wrote, not a
default. *Authority:* R6, plus §2.2's measurement that the warning branch is unreachable.

**R8 — the judge walk is a NEW executable.** Not an extension of
`scripts/deploy/post_apply_verify.py`, which requires `terraform output` and AWS credentials.
The walk must run from a bare checkout with nothing but a URL. **`dsn_unset` is a PASS with a
named reason, not a failure**, and the walk must say those words: *"the origin is up, the
route is reachable, and the SSM parameter is the founder's remaining step."* A walk that
exits red today would teach its reader to ignore it tomorrow.

**R9 — `tests/deploy/test_furl_compression.py` is re-recorded, not deleted, skipped, or
added to a red list.** *Authority:* the standing prohibition on lowering a floor, raising a
skip ceiling, or adding a known-red exemption. Its 30 errors are the correct behaviour of a
ratchet whose subject moved; the answer is to move the declaration to the new measurement and
name the build.

**R10 — the walk drives what the artefact itself declares.** The EvidenceBundle at
`console/fixtures/bundles/demo-cloud/frames/*.json` carries 18 frames, each with a `key` of
the form `"POST /v1/permits/<uuid>/merge"` plus the request body — a machine-readable,
already-committed enumeration of every request the console makes, and the REPLAY counterpart
of each. The walk reads it (from the served origin where possible) rather than re-deriving a
list, so LIVE and REPLAY are driven from one source. A 17th declared resource with no frame
is a D7 violation and the walk must say so.

**R11 — EVERY worker reports BOTH the junitxml numbers and the terminal summary, BEFORE and
AFTER, and a disagreement between them is a STOP.** *Authority:* §1.2. Do not proceed, do not
re-record anything, report to the lead.

**R12 — no worker touches the SSM parameter, prints a DSN, runs `terraform apply`, or
redeploys the Lambda.** Build and verify locally. The orchestrator deploys.

---

## 4. THE ORDER OF WORK

    W1  reproducibility + the LIVE build input        ─┐
    W3  declare the beat (console source)             ─┼─> both must land before the
                                                       │   rebuild that W5 measures
    W2  the artefact-mode refusal (guard + test)      ─┘
    W4  the judge walk                (independent; consumes the URL, not the build)
    W5  re-record the ceiling + cost  (depends on W1, W2, W3 — measures the rebuilt package)
    W6  docs true                     (depends on W1..W5 — records what actually happened)

W1, W2, W3 and W4 may run concurrently: their file sets are disjoint. W5 is the only worker
that may rebuild the package for measurement, and it does so **after** W1 and W3 have landed.

---

## 5. RULES REPEATED IN EVERY BRIEF (no exceptions, no worker is special)

1. **NEVER `terraform apply`. NEVER redeploy the Lambda.** Build and verify locally.
2. **NEVER write `/mainline/demo/cockroach_dsn`. NEVER print a DSN or any credential.**
   Never suggest using the `.env` DSN — it holds ALL on 417 objects and the URL is
   `authorization_type = NONE`.
3. **No shortcuts.** No `continue-on-error`, no `|| true`, no `-k`, no `--deselect`, no new
   `skip`, no lowered floor, no raised skip ceiling, no known-red exemption for a green.
4. **Never weaken `docs/HONESTY.md`, `docs/CI-STATE.md`, a ratchet or an assertion.**
5. **Ask which side is AUTHORITATIVE, never which is easier to move.**
6. Report `--crdb=reuse` full-suite numbers from `--junitxml` **and** the terminal summary,
   BEFORE and AFTER. Baseline: **576 / 575 passed / 0 failed / 0 errors / 1 skipped**.
   Disagreement between XML and terminal is a STOP (R11).
7. Touch only the files you own. If a file you need is owned by another worker, report it;
   do not edit it.
8. REUSE: every new file carries an SPDX header, or a `.license` sidecar if its format
   admits no comments (`.json`). `scripts/qa/check_reuse.py` is the checker.

---

## 6. WHAT "DONE" MEANS FOR THE WAVE

* A package is built whose `web/assets/*.js` carry a **non-empty** `VITE_MAINLINE_API_BASE`
  **and** `VITE_MAINLINE_BUNDLE_URL`, proven by reading the zip.
* `build_lambda` **refuses** the package that shipped, and does not refuse the new one.
* The console declares 17 resources, `gate-run.schema.json` is registered as a verbatim copy,
  and `DemoDriver`'s not-declared panel is unreachable in that build.
* `scripts/deploy/judge_walk.py --base-url <live URL>` runs green today, with `dsn_unset`
  recorded as the honest answer, and writes `evidence/deploy/judge-walk.json`.
* The four byte constants are re-recorded from the rebuilt package with the build named;
  `139_264` is unmoved and re-derived; exactly one identity object is refused;
  `0 < largest_served < ceiling < largest_web_object`.
* `tests/deploy/test_furl_compression.py` is green — 30 errors gone by re-measurement.
* Demo-api suite is **576 / 575 / 0 / 0** after, from `--junitxml` and from the terminal.
* `evidence/deploy/APPLIED.md` and the docs that cite the console's bytes are true again.

---

## 7. THE SIX WORKERS — disjoint paths, literally enumerated

### W1 · `console-build-reproducible`
    verticals/mainline/apps/console/vite.config.ts
    verticals/mainline/apps/console/.env.demo
    scripts/deploy/console_repro.py                       (new)
    tests/deploy/test_console_repro.py                    (new)
    docs/deploy/console-build.md
    evidence/deploy/console-repro.json                    (new, + .license)

### W2 · `artefact-mode-refusal`
    scripts/deploy/build_lambda.sh
    scripts/deploy/build_lambda.ps1
    tests/deploy/test_console_artefact_mode.py            (new)
    evidence/deploy/console-mode.json                     (new, + .license)

### W3 · `gate-run-addressable`
    verticals/mainline/apps/console/src/data/resources.ts
    verticals/mainline/apps/console/src/data/contracts.ts
    verticals/mainline/apps/console/src/data/types.generated.ts
    verticals/mainline/apps/console/contracts/gate-run.schema.json   (new, + .license)
    verticals/mainline/apps/console/src/features/gate/DemoDriver.tsx
    verticals/mainline/apps/console/tests/unit/data/resources.test.ts
    verticals/mainline/apps/console/tests/unit/data/contracts.test.ts
    verticals/mainline/apps/console/tests/unit/data/types.test.ts

### W4 · `judge-walk`
    scripts/deploy/judge_walk.py                          (new)
    tests/deploy/test_judge_walk.py                       (new)
    evidence/deploy/judge-walk.json                       (new, + .license)

### W5 · `ceiling-and-cost-re-record`
    verticals/mainline/apps/demo-api/tests/test_response_contract.py
    verticals/mainline/apps/demo-api/tests/test_static_site.py
    tests/deploy/test_furl_compression.py
    docs/decisions/response-ceiling-authoritative-tree.md

### W6 · `docs-true`
    evidence/deploy/APPLIED.md
    docs/CI-STATE.md
    docs/ci/cluster-lane-package.md
    docs/deploy/COST-BOUND.md
    docs/deploy/RUNBOOK.md
    docs/deploy/JUDGE-PACK.md
    tests/deploy/test_docs_are_true.py

No path appears twice. `docs/leads/package-and-verify-plan.md` is the lead's and is owned by
nobody else.

---

## 8. THE THING TO KEEP IN VIEW

The console's own source says it best, about badges, and it is the whole plan in one line:

> *"A selection recorded here and a transport built over there are two places for one fact to
> live, and the day they disagree is the day the badge is decoration."*
> — `src/app/source-select.ts:42-44`

`probe_console` and `source-select.ts` were two places holding one fact. They disagreed. The
badge became decoration, and a judge would have read it. Put the check on the bytes.
