<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CONSOLE-LIVE — the deployed console must talk to the kernel it is sitting on

**Lead:** console-live. **Date:** 2026-08-14. **Workers:** 6.
**Target:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

A judge opens that URL today and sees a recorded EvidenceBundle with no way to press the
one button the product exists to demonstrate. Everything else in this repository is
downstream of that first impression. The console is already honest about what it cannot
do. **The fix is to make it able, never to soften what it says.**

---

## 0. The baseline, measured by this lead on 2026-08-14

Every number below was produced by a command run against the live URL or the working tree.
Nothing here is quoted from a document.

### 0.1 What the live URL serves

| Request | Result |
|---|---|
| `GET /` | **200**, 4,655 B, 0.70 s — the static console shell serves |
| `GET /assets/index-DzVoV1YM.js` (no `accept-encoding`) | **413** `response_too_large` — 433,564 B against a 139,264 B ceiling; the refusal names `accept-encoding: gzip` as the first thing to try |
| `GET /assets/index-DzVoV1YM.js` (`--compressed`) | **200**, 124,177 B |
| `GET /assets/index-C498vmEA.css` | **200**, 3,569 B |
| `GET /v1/health` | **503**, `ok=false`, `reason="dsn_unset"` |
| `POST /v1/demo/gate-run` | **503**, `kind="dsn_unset"` — **NOT 404. The route exists and is reachable.** |

Both API answers name the cause exactly:
`SSM GetParameter '/mainline/demo/cockroach_dsn' in ap-southeast-1 answered HTTP 400: {"__type":"ParameterNotFound"}`.

The 413 is correct behaviour and is **not** in scope: the ceiling is deliberate, the
refusal is self-describing, and a browser sends `accept-encoding: gzip`.

### 0.2 What was compiled into the deployed artefact — the proof of FAULT 1

Extracted from the served bundle, not inferred:

```
VITE_MAINLINE_API_BASE:""
VITE_MAINLINE_BUNDLE_URL:"./bundle/"
VITE_MAINLINE_LOG_VKEY:""
MODE:"demo"
buildId:"dev"
signaturePath:"unknown"
```

`src/app/source-select.ts:104` treats `""` as unset (`trimmed()`), so exactly one source is
configured, `switchable` is false, and the header reads **`TRANSPORT REPLAY`** with no
control. The bundle it plays (`fixtures/bundles/demo-cloud/manifest.json`) carries
`"staged": true`, which is why the badge reads `REPLAY (staged)`. **Every byte on that
screen is a recording.** The founder's reading of the banner is exactly right.

`buildId:"dev"` is a **second** shipped defect in the same artefact: `MAINLINE_BUILD_ID` was
not supplied, so the honesty chrome cannot name the artefact the screenshot came from —
which `docs/deploy/console-build.md` §1 says is the whole reason that field exists.

The deployed JS contains **zero** occurrences of `gate-run`, `gate_run` or `demo_gate_run`.

### 0.3 Why the existing packaging warning did not fire — and could never have fired

`scripts/deploy/build_lambda.sh:879` is reached only when `console["configured"]` is falsy.
`probe_console()` (`:618`) builds that map with
`ENV_LITERAL = re.compile(r'(VITE_MAINLINE_[A-Z_]+):"((?:[^"\\]|\\.)*)"')` and
`found.setdefault(key, value)` — **keyed on the variable NAME, with no test on the VALUE.**
Vite emits `VITE_MAINLINE_API_BASE:""` for every build, because `.env.demo` declares the
variable empty. So `found` is never empty, the `else` branch at `:879` is **dead code**, and
the packer printed a cheerful

```
console   VITE_MAINLINE_API_BASE=(empty), VITE_MAINLINE_BUNDLE_URL=./bundle/
```

while packaging a REPLAY console for an origin with a live kernel behind it. The machinery
to notice existed; it was measuring the wrong thing.

### 0.4 The console side — the declaration gap, exactly

* `src/data/resources.ts` — **16** `declare()` calls; `demo_gate_run` is not one of them.
  `RESOURCE_KEYS` lists the same 16 and a module-load assertion pins the two together.
* `src/data/contracts.ts` — **17** `CONTRACT_SOURCES` entries; `gate-run.schema.json` is not
  one of them.
* `contracts/` — 17 schemas; **no** `gate-run.schema.json`.
* `src/features/gate/DemoDriver.tsx` — complete. Four controls, four beats, `Sqlstate` and
  `ConstraintName` primitives, the `parsed`-is-a-weakened-diagnosis paragraph, the whole
  thing. It is mounted at `src/app/App.tsx:152` under `DEMO_SURFACE_ID = 'gate'`, and
  `src/app/composition.tsx:346` **does** provide `GateTransportContext.Provider`. The
  screen exists and the transport reaches it. It renders the not-declared panel because
  `RESOURCES.has('demo_gate_run')` is false, and it **correctly refuses** to reach the
  endpoint with a bare `fetch`.

**There is no missing screen. There is a missing declaration.**

### 0.5 The banner's false sentence — FAULT 2, located

`src/features/gate/DemoDriver.tsx:84-87`, third element of `DECLARATION_GAP`:

> `…app.py — Route("POST", "/v1/demo/gate-run", "demo_gate_run") plus SCHEMA_IDS["demo_gate_run"]. The handler is complete (gate_run.py) and is reachable through handle_transition today; the route table declares the four kernel POSTs and no demo route, so the endpoint 404s.`

Measured against the tree: `app.py:229` carries
`Route("POST", "/v1/demo/gate-run", "demo_gate_run")` as the **seventeenth** route, with a
docstring at `:180` explaining why. Measured against the wire: the live URL answers **503
`dsn_unset`**, not 404. The sentence is false in the tree and false on the wire.

`docs/deploy/gate-run-contract.md` §9 carries the same dead claim
(*"`POST /v1/demo/gate-run` is not yet routed"*) and must move with it.

`SCHEMA_IDS` in `envelope.py:116` genuinely does still lack a `demo_gate_run` entry — that
half of the sentence is true — but the success path does not use it:
`transitions.py` builds its own envelope with `gate_run.GATE_RUN_SCHEMA_ID`.

### 0.6 The couplings a declaration will break — found before anyone writes code

Three Python tests read `resources.ts` from disk and will go **red** the moment a
seventeenth `declare()` lands. This is not a surprise to be discovered by a worker; it is
scope, assigned in advance to W3:

| File | What breaks |
|---|---|
| `demo-api/tests/test_routes_gate_run.py` | `_CONSOLE_ROUTE_COUNT = 16`; `assert len(declared) == 16`; `assert routed - declared == {DEMO_ROUTE}` |
| `demo-api/tests/test_envelope.py:110` | `test_the_console_declares_sixteen_resources` — `assert len(declared) == 16` |
| `demo-api/tests/test_seed_covers_every_console_resource.py` | parses `RESOURCE_KEYS` and drives every key against the seeded cluster |

### 0.7 REPLAY has no gate-run frame

`fixtures/bundles/demo-cloud/manifest.json` carries 18 frame keys. **None** is
`POST /v1/demo/gate-run`. `capture-plan.demo.json` does not name it either.
`src/data/bundle.ts:400` already refuses with *"bundle … has no frame for this request"*.

### 0.8 The suite baseline

Command (`uv` is not on PATH; this interpreter is the only thing that runs the suite):

```
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -m pytest \
  verticals/mainline/apps/demo-api/tests --crdb=reuse -q --junitxml=<path>
```

**Measured by this lead, 2026-08-14, from `--junitxml` and not from the terminal tail:**

```
tests=576  failures=0  errors=0  skipped=1  time=188.684s
passed=575
```

which is the ratified baseline **576 / 575 / 0 / 0**, reproduced rather than quoted. The one
skip is `test_gate_run.py:1294 test_payload_validates_against_the_json_schema` — `jsonschema`
is not a workspace dependency, and the hand-written structural check is what runs today.

Every worker reports `--junitxml` counts BEFORE and AFTER their own change. **Failures may
not increase. Skips may not increase.** Raising the skip ceiling to get a green is the
prohibited move, not a shortcut.

---

## 1. Rulings

The brief leaves several things open. Each ruling below names its authority. **A worker
that finds a ruling wrong argues on the record and stops; it does not quietly do the other
thing.**

### R1 — The console is authoritative. `test_routes_gate_run.py` moves, and it moves UP.

**Authority:** the ratified tiebreaker — *the console and the committed JSON schemas are
authoritative for what the demo must carry; seed and tests are both checked against them,
either may lose.*

`test_routes_gate_run.py` today pins `routed - declared == {DEMO_ROUTE}` and
`len(declared) == 16`. Once the console declares the resource the correct assertion is
`declared == routed`, both **17** — which is **strictly stronger** than "differs by exactly
one row I have named". That is a ratchet **up**.

**Explicitly forbidden:** deleting the test, `xfail`, `skip`, loosening `==` to `<=`,
raising `_CONSOLE_ROUTE_COUNT` without also collapsing the set difference to empty. The
docstring must be rewritten to say what it now pins and to record that the gap it was
written against closed on 2026-08-14.

### R2 — Fix the banner by making its false clause true, not by deleting the panel.

**Authority:** brief (b). The panel is the honest rendering **if the declaration is ever
removed**, so it stays. Entries 1 and 2 of `DECLARATION_GAP` name the console's own two
files and remain the true remedy for a regression. Entry 3 is replaced with a sentence that
matches the tree and the wire: the route has been present since 2026-08-13, the live URL
answers 503 `dsn_unset`, and the remaining API-side item is `SCHEMA_IDS`. **No sentence in
that array may claim a 404 that the wire does not produce.**

### R3 — The control is present in REPLAY too, and REPLAY tells the truth about its bundle.

**Authority:** D7, as stated in `src/app/source-select.ts` — LIVE and REPLAY are one line of
composition and one badge, **never a code path**. A control shown in LIVE and hidden in
REPLAY is a second code path.

Measured (§0.7): no gate-run frame exists in any bundle. `bundle.ts:400` already produces
the honest absence. That is the correct REPLAY behaviour today and is a **named gap**, not a
defect to paper over.

**Capturing a real gate-run frame requires a live capture against the cloud, which requires
the SSM secret — the founder's step. It is OUT OF SCOPE for this wave. NO WORKER MAY
HAND-AUTHOR A GATE-RUN FRAME INTO ANY BUNDLE, edit a manifest digest, or re-seal a bundle
around invented bytes.** That is the exact laundering this repository exists to refuse.

### R4 — The packaging guard REFUSES, and it refuses on the VALUE.

**Authority:** brief (c) — *"a packaging step that produces a REPLAY console for an origin
that has a live kernel behind it should fail, not warn."*

The existing check is dead code for the measured reason in §0.3. `probe_console()` must
apply the same `trimmed()` semantics `selectSource` applies — **an empty string is unset** —
and the packer must take an explicit, **required** declaration of the intended transport and
refuse when the dist does not match it. A refusal, through the existing `refuse()` path, is
the only acceptable outcome. `continue-on-error` and `|| true` remain banned.

### R5 — `MAINLINE_BUILD_ID` joins the same gate.

**Authority:** this lead, on `docs/deploy/console-build.md` §1 (*"a screenshot must name the
artefact it came from"*) and the measurement `buildId:"dev"` in §0.2.

An artefact that cannot name itself is the same class of defect as one that cannot name its
source, and it shipped in the same build for the same reason. It **refuses** under
`--console-transport live`; it **warns** for a local build.

### R6 — Every sentence the console prints about another file is pinned by a test that reads that file.

**Authority:** brief (b) — the banner went stale because nothing checked it, and a second
stale sentence would be the same failure with a different noun.

Two obligations. (i) A console unit test asserts that every repository path named in a
remedy line **exists**. (ii) The not-declared panel must be proven **unreachable with the
real registry** while its own render stays covered by a stubbed registry — the honest
fallback keeps its test, it just stops being what a judge sees.

### R7 — The local proof drives a real browser against the real handler.

**Authority:** brief (d) — *"a browserless test of `selectSource` is not enough on its own,
because the defect that shipped was a build-time value, not a logic error."*

`scripts/deploy/local_furl.py` already calls `mainline_demo_api.app.handler` **unstubbed**
over `$MAINLINE_WEB_ROOT`. Chromium is installed (`chromium-1228` under
`~/AppData/Local/ms-playwright`) and `@playwright/test` is a devDependency.

**There is no `playwright.config.ts` and this wave MUST NOT create one.**
`tests/browser/gate.spec.ts` names it as owned by the `cinema-conformance-harness` worker
and PL-2 is red by design. The proof is a standalone driver on paths this wave owns, using
the Playwright **library** API — never `playwright test`, never a new config, never an edit
under `tests/browser/**`.

### R8 — `dsn_unset`, rendered honestly, IS the passing condition.

**Authority:** the brief — *"your work is verified by proving the console ATTEMPTS the live
kernel and renders that refusal honestly, which is itself the correct behaviour and a good
demo beat."*

The acceptance asserts: the chrome reads **LIVE**; the four controls exist; pressing one
issues `POST /v1/demo/gate-run` **to the page's own origin**; and the answer is rendered
verbatim. A green that required a working DSN would be a green nobody in this wave could
run.

**Never write the SSM parameter. Never print a DSN or any credential. Never use the `.env`
DSN as a substitute** — measured, `mainline-sql` holds ALL on 417 objects while
`mainline_api` holds CONNECT/USAGE/SELECT/UPDATE/INSERT/EXECUTE only, and the URL is
`authorization_type = NONE`.

### R9 — No deploy, from anyone, for any reason.

**No `terraform apply`. No Lambda update. No S3 upload. No `aws lambda update-function-code`.**
Build to `dist/`, package to a local zip if a worker needs one, verify locally. **The
orchestrator deploys.** A worker that believes a deploy is required stops and says so.

### R10 — The persistence reading is stale against the amended contract; widen it, never narrow it.

**Authority:** the committed schema is authoritative.

`DemoDriver.tsx:144` declares `GateRunPersistence { identical, tables, note }`. The contract
now **requires** `before, after, identical, self_persisted, self_evidence, concurrent_writes,
tables, note`, and its own §`persistence_check` description records that the verdict keys on
**`self_persisted`**, not on `identical`. A screen showing only `identical` shows the field
the contract says is *not* the basis of the verdict. Add `self_persisted` and
`concurrent_writes` beside it. **Remove nothing.**

---

## 2. The six workers

Paths are literally enumerated and disjoint. **No worker touches a path another worker
owns.** A worker that believes it needs to stops and reports to this lead.

| # | Worker | Owns |
|---|---|---|
| W1 | `console-resource-declaration` | `resources.ts`, `contracts.ts`, `contracts/gate-run.schema.json{,.license}`, `types.generated.ts`, 2 unit tests |
| W2 | `console-gate-screen` | `DemoDriver.tsx`, `demo-driver.module.css`, `composition.test.tsx`, new `demo-driver.test.tsx` |
| W3 | `demo-api-agreement` | `envelope.py` + the 3 Python tests that read `resources.ts` |
| W4 | `packaging-transport-guard` | `build_lambda.sh`, `build_lambda.ps1`, `deploy.sh`, `deploy.ps1`, new `tests/deploy/test_console_transport_guard.py` |
| W5 | `local-live-proof` | new `console_live_acceptance.py`, new `drive-console.mjs`, `evidence/deploy/console-live.json{,.license}` |
| W6 | `docs-true-console-live` | `console-build.md`, `gate-run-contract.md`, `RUNBOOK.md`, `JUDGE-PACK.md`, `tests/deploy/test_docs_are_true.py` |

**Order.** W1 has no dependency and unblocks W2 and W3. W4 and W6 are independent of all of
them. W5 depends on W1 + W2 (it drives the finished screen) and on W4 (it invokes the guard).

```
W1 ──┬──► W2 ──┐
     └──► W3   ├──► W5
W4 ─────────────┘
W6 (independent)
```

---

## 3. Acceptance for the wave

1. `resources.ts` declares **17** resources including `demo_gate_run`; the module-load
   assertion still passes.
2. `contracts.ts` registers `gate-run.schema.json` as a **verbatim** copy of the demo-api's,
   and a test compares the two JSON-pointer by JSON-pointer in both directions.
3. `DemoDriver` renders all four beats with their SQLSTATEs; `23514
   gate_closed_when_issued` is on screen and comes from the payload, never from a literal.
4. No sentence in the console claims a 404 the wire does not produce, and a test reads the
   files those sentences name.
5. `build_lambda` **refuses** to package a REPLAY-only dist under `--console-transport live`,
   and refuses a `dev` build id in that mode. A falsification test proves the refusal fires.
6. A real chromium, against `local_furl.py` running the real `app.handler` over a freshly
   built dist, shows **LIVE** in the chrome, presses `RUN ALL`, and renders the honest
   `dsn_unset` answer from the page's own origin.
7. `--crdb=reuse --junitxml` numbers reported BEFORE and AFTER. **576/575/0/0 is a floor.**
   Failures may not increase. Skips may not increase.
8. `pnpm run ci` clean in the console workspace (lint at `--max-warnings 0`, typecheck,
   vitest, build, budgets, licences).
9. Nothing deployed. `custody-chain`, `schema`, `db` and PL-2 remain red by design and
   untouched.

---

## 4. The briefs

**These five rules are repeated in every brief because every brief must be readable alone.**

* **NO SHORTCUTS.** Never lower a floor, raise a skip ceiling, add a known-red exemption for
  a green, or weaken `HONESTY.md`, `CI-STATE.md`, a ratchet or an assertion.
  `continue-on-error` and `|| true` are banned. When two sides disagree, ask **which is
  authoritative** — never which is easier to move. The console and the committed JSON schemas
  are authoritative for what the demo must carry.
* **NO DEPLOY.** Never `terraform apply`. Never redeploy the Lambda. No S3 upload, no
  `aws lambda update-function-code`. Build and verify locally; the ORCHESTRATOR deploys.
* **NO SECRETS.** Never write the SSM parameter `/mainline/demo/cockroach_dsn`. Never print a
  DSN or any credential. Never suggest using the `.env` DSN — it is `mainline-sql`, which
  holds ALL on 417 objects, and the demo URL is `authorization_type = NONE`.
* **MEASURE.** Report full-suite `--crdb=reuse` numbers from `--junitxml` BEFORE and AFTER.
  Baseline **576 / 575 / 0 / 0**. `uv` is NOT on PATH:
  `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -m pytest …` is the only thing that
  runs the suite.
* **STAY IN YOUR PATHS.** The paths under your `owns` are yours. Every other path in this
  repository belongs to somebody else. If you believe you need one, stop and report.

### W1 — `console-resource-declaration`

**Owns** `console/src/data/resources.ts`, `console/src/data/contracts.ts`,
`console/contracts/gate-run.schema.json`, `console/contracts/gate-run.schema.json.license`,
`console/src/data/types.generated.ts`, `console/tests/unit/data/resources.test.ts`,
`console/tests/unit/data/contracts.test.ts` (all under
`verticals/mainline/apps/console/`).

Make `demo_gate_run` addressable. Copy
`verticals/mainline/apps/demo-api/contracts/gate-run.schema.json` **verbatim** — byte for
byte, no reformatting, no reordering — to the console's `contracts/`, with a `.license`
sidecar matching its siblings (`SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2`; JSON admits
no comment syntax, which is why sidecars exist). Register it in `CONTRACT_SOURCES` as an
explicit `?raw` import in alphabetical position — the header explains why the list is explicit
rather than an `import.meta.glob`, and that reasoning holds. Add the seventeenth `declare()`:
`declare('demo_gate_run', 'POST', '/v1/demo/gate-run', <backtick>${C}gate-run.schema.json<backtick>, 'kernel', <one line of purpose>)`,
and add `'demo_gate_run'` to `RESOURCE_KEYS` in sorted position. The module-load assertion at
`resources.ts:242` compares the two lists and must still pass. The template takes **no** path
parameter: the subject is the seeded demo permit, resolved server-side, so a judge cannot
point the driver at somebody else's row.

Regenerate `types.generated.ts` with `node scripts/gen-types.ts` — it reads
`readdirSync(contracts/)`, so the new schema is picked up automatically. Do not hand-edit the
generated file; `tests/unit/data/types.test.ts` reads it as text and refuses `any` and stray
index signatures.

Extend both owned tests. `contracts.test.ts:55` asserts
`registry.ids().length === CONTRACT_SOURCES.length` and follows automatically; **add** a
verbatim-copy test comparing the two `gate-run.schema.json` files JSON-pointer by
JSON-pointer **in both directions**, modelled on the `refusal.schema.json` test at `:85`. That
test is what stops the copy drifting. `createContractRegistry()` calls `compileAll()`, which
refuses any keyword the validator does not implement, so a vacuous contract raises at startup.
Run it: this schema uses `allOf`/`if`/`then`/`else`/`oneOf`/`const`/`enum` and a `$ref` to
`https://spec.trappoint.org/1.0/wire/refusal.schema.json`, resolved through the already
registered `refusal.schema.json`. **If compilation raises, that is a real finding — report it;
do not delete the keyword and do not stub the `$ref`.**

Three Python tests read `resources.ts` from disk and will go red on your change. **That is
W3's assigned scope, not yours.** Do not edit them.

Done when: `pnpm run lint && pnpm run typecheck && pnpm run test && vite build` is clean;
`RESOURCES.size === 17`; the verbatim-copy test passes both directions.

**NO SHORTCUTS** — the copy is verbatim; if the demo-api schema looks wrong, argue on the
record, never edit either copy to make them agree. **NO DEPLOY** — never `terraform apply`,
never redeploy the Lambda. **NO SECRETS** — never write the SSM parameter, never print a DSN.
Report `--junitxml` counts before and after (baseline 576/575/0/0).

### W2 — `console-gate-screen`

**Owns** `console/src/features/gate/DemoDriver.tsx`,
`console/src/features/gate/demo-driver.module.css`,
`console/tests/unit/app/composition.test.tsx`,
`console/tests/unit/gate/demo-driver.test.tsx` (new). **Depends on W1.**

Three jobs, and the first is the one a judge sees.

**(1) Kill the false sentence.** `DemoDriver.tsx:84-87`, third element of `DECLARATION_GAP`,
ends *"the route table declares the four kernel POSTs and no demo route, so the endpoint
404s."* False in the tree — `app.py:229` carries
`Route("POST", "/v1/demo/gate-run", "demo_gate_run")` as the seventeenth route — and false on
the wire: the live URL answers **503 `dsn_unset`**, measured 2026-08-14. Replace that entry
with a true one (route present since 2026-08-13; the remaining API-side item is `SCHEMA_IDS`).
**Do not delete the panel or the array.** Per ruling R2 it is the honest rendering if the
declaration is ever removed; entries 1 and 2 name the console's own files and stay. No
sentence in that array may claim a 404 the wire does not produce.

**(2) Render the four beats.** With W1 landed, `RESOURCES.has('demo_gate_run')` is true and
the driver stops short-circuiting. The report component already exists and is good: keep its
voice. Verify `23514 gate_closed_when_issued` and `P0001 mainline.fn_permit_merge_gate` reach
the screen through `Sqlstate` and `ConstraintName` **from the payload**, never from a literal
in this module — D18, enforced by what the file does not contain. Per ruling **R10**, widen
the `GateRunPersistence` reading: the contract requires
`before, after, identical, self_persisted, self_evidence, concurrent_writes, tables, note`,
and its own description records that the verdict keys on **`self_persisted`**, not
`identical`. Render `self_persisted` and `concurrent_writes` beside `identical`. **Remove
nothing.**

**(3) Pin it so it cannot go stale again (ruling R6).** In the new `demo-driver.test.tsx`:
assert every repository path named in a remedy line **exists on disk**; assert the
not-declared panel is **unreachable with the real registry**; keep the panel's own render
covered by a stubbed registry, so the honest fallback keeps its test and merely stops being
what a judge sees. Update the two `DemoDriver` cases in `composition.test.tsx` (~581, ~600).

Per ruling **R3**: the four controls are present in REPLAY too. No bundle carries a
`POST /v1/demo/gate-run` frame (measured: 18 keys in `fixtures/bundles/demo-cloud/manifest.json`,
none this one) and `src/data/bundle.ts:400` already refuses honestly with *"bundle … has no
frame for this request"*. That refusal **is** the correct REPLAY rendering; hiding the button
in REPLAY would be the second code path D7 forbids. **You may not hand-author a gate-run frame
into any bundle, edit a manifest digest, or re-seal a bundle around invented bytes.**

`src/features/gate` is the EVIDENCE register: mono for anything the database emitted, no
easing over 160 ms, no `motion`, no `@react-three/*`, nothing a screenshot could not reproduce.

Done when: `pnpm run ci` is clean; the four controls render; no false sentence remains.

**NO SHORTCUTS** — never soften what the console says to make a test pass. **NO DEPLOY** —
never `terraform apply`, never redeploy the Lambda. **NO SECRETS** — never write the SSM
parameter, never print a DSN. Report `--junitxml` counts before and after (576/575/0/0).

### W3 — `demo-api-agreement`

**Owns** `demo-api/src/mainline_demo_api/envelope.py`,
`demo-api/tests/test_routes_gate_run.py`, `demo-api/tests/test_envelope.py`,
`demo-api/tests/test_seed_covers_every_console_resource.py` (all under
`verticals/mainline/apps/`). **Depends on W1.**

W1's seventeenth `declare()` turns three of your tests red by design, because they read
`resources.ts` from disk and count sixteen. Ruling **R1** governs: the console is
authoritative and these tests move — **upward**.

`test_routes_gate_run.py` asserts `_CONSOLE_ROUTE_COUNT = 16`, `len(declared) == 16`, and
`routed - declared == {DEMO_ROUTE}`. With the console declaring it, the correct assertion is
`declared == routed`, both **17** — strictly stronger than "differs by exactly one row I have
named", because it now admits **no** undeclared route rather than one known exception.
**Forbidden:** deleting the test, `xfail`, `skip`, loosening `==` to `<=`, or raising the
count without collapsing the set difference to empty. Rewrite the docstring to say what it now
pins and to record that the gap it was written against closed on 2026-08-14 — the file's whole
value is that it explains the defect it prevents. `test_envelope.py:110`
(`test_the_console_declares_sixteen_resources`) needs the same treatment, name included; its
`sum(... == "GET") == 12` companion is unchanged because the new resource is a POST.

`test_seed_covers_every_console_resource.py` parses `RESOURCE_KEYS` and drives every key
against the seeded cluster. `demo_gate_run` has no path parameter and is not a read, so the
`_ABSENT`-subject machinery does not apply. **Measure what actually happens before deciding**
— run it, read the failure, then handle the key explicitly and by name with a comment saying
why, rather than widening a filter that would silently excuse a future resource too. An
exemption that admits one named endpoint is a decision; a loosened predicate is a hole.

In `envelope.py:116`, add the `demo_gate_run` entry to `SCHEMA_IDS`. **First establish whether
it changes observable behaviour**: the success path does not use it (`transitions.py` builds
its own envelope with `gate_run.GATE_RUN_SCHEMA_ID`), but `app.py:551` and `:619` call
`SCHEMA_IDS.get(matched.key)` on other paths and currently degrade to `null` for this key.
Report what you measured. The docstring above `SCHEMA_IDS` calls itself "a transcription of
the console's sixteen" and must be updated to say seventeen and name the one that is not a
console read contract.

Do not touch `app.py`'s route table — it is already correct, and the live URL proves it by
answering 503 rather than 404. Do not touch `gate_run.py` or `transitions.py`.

Done when: the demo-api suite is green at **≥ 576 tests, 0 failures, 0 errors, ≤ 1 skip** with
`--crdb=reuse`, in default and randomised order.

**NO SHORTCUTS** — no `xfail`, no `skip`, no lowered floor, no `continue-on-error`, no
`|| true`. **NO DEPLOY** — never `terraform apply`, never redeploy the Lambda. **NO SECRETS**
— never write the SSM parameter, never print a DSN, never use the `.env` DSN. Report
`--junitxml` counts before and after (576/575/0/0).

### W4 — `packaging-transport-guard`

**Owns** `scripts/deploy/build_lambda.sh`, `scripts/deploy/build_lambda.ps1`,
`scripts/deploy/deploy.sh`, `scripts/deploy/deploy.ps1`,
`tests/deploy/test_console_transport_guard.py` (new).

A packaging step that produces a REPLAY console for an origin with a live kernel behind it
must **fail, not warn**. Today it does neither, and the reason is measured rather than guessed.

`probe_console()` at `build_lambda.sh:618` collects
`ENV_LITERAL = (VITE_MAINLINE_[A-Z_]+):"…"` into `found` via `found.setdefault(key, value)` —
**keyed on the variable NAME, never testing the VALUE.** Vite emits
`VITE_MAINLINE_API_BASE:""` for every build because `.env.demo` declares the variable empty.
So `found` is never empty, `if console["configured"]:` at `:875` is always true, and the
`else` at `:879` is **dead code that has never executed and cannot**. The deployed artefact is
the proof: it carries `VITE_MAINLINE_API_BASE:""` and `VITE_MAINLINE_BUNDLE_URL:"./bundle/"`,
and the packer printed `console VITE_MAINLINE_API_BASE=(empty), VITE_MAINLINE_BUNDLE_URL=./bundle/`
and packaged it.

Fix per ruling **R4**. Make `probe_console()` apply the same `trimmed()` semantics
`src/app/source-select.ts:104` applies — **an empty string is UNSET** — and report the
*effective* sources, not the present keys. Add a **required** declaration of intended transport
(e.g. `--console-transport live|replay|both`) and refuse, through the existing `refuse()`
mechanism, when the dist does not carry what was declared. Naming it explicitly is the point:
a guard that infers intent has to be right about intent; this one only compares two things a
human wrote down. Per ruling **R5**, in `live` mode also refuse a `buildId` of `dev` —
measured, the deployed artefact carries `buildId:"dev"`, so the honesty chrome cannot name the
artefact a screenshot came from, which `docs/deploy/console-build.md` §1 says is the entire
reason that field exists. Warn rather than refuse for a local build. Keep the existing
"carries neither" case as a refusal too, now that it can actually fire.

`deploy.sh:822` invokes `bash "$BUILD_LAMBDA" --arch "$ARCH" --out "$LAMBDA_ZIP"` and `:821`
the PowerShell twin; both must pass the new flag, and `build_lambda.ps1` must stay in step
with the `.sh`. `build_lambda.sh` is a shell wrapper around embedded Python — read enough of
it to keep the two halves consistent.

Write `tests/deploy/test_console_transport_guard.py` beside `test_furl_compression.py` and
`test_post_apply_verify.py`. It must include a **falsification** case: a synthetic dist
carrying exactly the literals the live artefact carries (`VITE_MAINLINE_API_BASE:""`,
`VITE_MAINLINE_BUNDLE_URL:"./bundle/"`, `buildId:"dev"`) must be **REFUSED** under
`--console-transport live`, and the same dist **accepted** under `--console-transport replay`.
A guard with no test that proves it fires is a guard nobody has run.

**You do not own `dist/` and must not build the console.** Construct synthetic asset files in
a temporary directory. Do not edit `.env.demo`, `vite.config.ts`, or anything under
`verticals/mainline/apps/console/`.

Done when: the falsification test fails without your change and passes with it; `ruff` and
`mypy --strict` are clean over the files you touched.

**NO SHORTCUTS** — a refusal, never a warning; `continue-on-error` and `|| true` are banned;
never raise a ceiling to make a build pass. **NO DEPLOY** — never `terraform apply`, never
redeploy the Lambda, never upload the zip you build. **NO SECRETS** — never write the SSM
parameter, never print a DSN. Report `--junitxml` counts before and after (576/575/0/0).

### W5 — `local-live-proof`

**Owns** `scripts/deploy/console_live_acceptance.py` (new),
`verticals/mainline/apps/console/scripts/drive-console.mjs` (new),
`evidence/deploy/console-live.json` (new), `evidence/deploy/console-live.json.license` (new).
**Depends on W1, W2, W4.**

Prove the fix against the **real handler**, in a **real browser**. A browserless test of
`selectSource` is not enough on its own: the defect that shipped was a build-time value, not a
logic error, and only a build plus a browser catches that class.

`scripts/deploy/local_furl.py` is the harness and already exists. It translates HTTP into a
Lambda payload-format-2.0 event, calls `mainline_demo_api.app.handler(event, None)`
**unstubbed**, and serves `$MAINLINE_WEB_ROOT` through the same `static_site` module the
Lambda uses. It stamps `X-Mainline-Emulator: local_furl` on every response so a transcript
taken against it can never be mistaken for one taken against the deployment — preserve that
distinction in your evidence file.

Your program: build the console with `VITE_MAINLINE_API_BASE` and `MAINLINE_BUILD_ID` set; run
the W4 guard over the resulting dist under `--console-transport live` and require it to
**pass**; start `local_furl.py` on a loopback port with `MAINLINE_WEB_ROOT` pointing at that
dist; drive chromium; write `evidence/deploy/console-live.json` with every measurement.

**Measured hazard that has bitten this repository before:** `docs/deploy/console-build.md` §1
records that `VITE_MAINLINE_API_BASE=/` in Git Bash on Windows becomes `C:/Program Files/Git/`
through MSYS path conversion — observed in a real artefact on 2026-08-10. Use PowerShell
(`$env:VITE_MAINLINE_API_BASE='/'`) or `MSYS_NO_PATHCONV=1`, and **always verify the compiled
value** with `grep -o 'VITE_MAINLINE_API_BASE:"[^"]*"' dist/assets/index-*.js` before trusting
the run.

Per ruling **R7**: there is **no** `playwright.config.ts` and you **must not create one**.
`tests/browser/gate.spec.ts` names it as owned by the `cinema-conformance-harness` worker and
PL-2 is red by design. Use the Playwright **library** API from your own `drive-console.mjs` —
never `playwright test`, never a config, never an edit under `tests/browser/**`. Chromium is
installed (`chromium-1228` under `~/AppData/Local/ms-playwright`) and `@playwright/test` is a
devDependency of the console workspace.

Assert, per ruling **R8**: (i) the honesty chrome reads **LIVE**, naming
`VITE_MAINLINE_API_BASE`, not REPLAY; (ii) `buildId` is not `dev`; (iii) the four controls
render (`data-testid="demo-control-merge|forge|admit|all"`); (iv) pressing **RUN ALL** issues
`POST /v1/demo/gate-run` **to the page's own origin** — capture it off the network log, do not
infer it; (v) the answer is rendered verbatim. **The kernel will answer 503 `dsn_unset`
because the SSM parameter is the founder's step and is not yours — and that, rendered
honestly, IS the passing condition.** A green that required a working DSN would be a green
nobody in this wave could run. Record the REPLAY build's behaviour for contrast.

Done when: the program is repeatable from a clean tree and its evidence file distinguishes the
emulator from the deployment.

**NO SHORTCUTS** — never stub the handler, never assert on a screenshot alone, never mark a
failing assertion advisory. **NO DEPLOY** — never `terraform apply`, never redeploy the
Lambda, never upload the dist you build; the ORCHESTRATOR deploys. **NO SECRETS** — never
write the SSM parameter `/mainline/demo/cockroach_dsn`, never print a DSN, never use the
`.env` DSN to make the 503 go away. Report `--junitxml` counts before and after (576/575/0/0).

### W6 — `docs-true-console-live`

**Owns** `docs/deploy/console-build.md`, `docs/deploy/gate-run-contract.md`,
`docs/deploy/RUNBOOK.md`, `docs/deploy/JUDGE-PACK.md`, `tests/deploy/test_docs_are_true.py`.
Independent of the other five; start immediately.

Documents here make claims that were true when written and are false now, and one is the same
false sentence the console shipped. `docs/deploy/gate-run-contract.md` §9 "Known gaps" says
*"**`POST /v1/demo/gate-run` is not yet routed.** `app.py`'s route table … declares the four
kernel POSTs and no demo route, so the endpoint 404s"*. Measured 2026-08-14: `app.py:229`
carries the route as the seventeenth, and the live URL answers **503 `dsn_unset`**. The same
§9 says *"The console does not declare `demo_gate_run`"*, which W1 closes. Rewrite those gaps
as **closed**, dated, and pointing at what closed them — do not delete the history, because a
gap that was real and is now shut is evidence the process works.

`docs/deploy/console-build.md` gains the new packaging guard: the required
`--console-transport` flag W4 adds, why it exists (`probe_console` keyed on variable NAME, so
`VITE_MAINLINE_API_BASE:""` always looked "configured" and the warning at `:879` was dead
code), and what the deployed artefact actually carried (`VITE_MAINLINE_API_BASE:""`,
`VITE_MAINLINE_BUNDLE_URL:"./bundle/"`, `buildId:"dev"`). The MSYS `C:/Program Files/Git/`
hazard note in §1 is measured and correct — **keep it**, and strengthen the surrounding text
so nobody treats "verify the compiled value" as optional.

`RUNBOOK.md` and `JUDGE-PACK.md`: bring every statement about what a judge sees at the demo
URL into line with what the URL serves. Do not overstate the fix — until the founder writes
the SSM parameter, LIVE mode answers `dsn_unset`, and the honest thing to tell a judge is that
the console attempts the kernel and renders the refusal. **That is a good demo beat and should
be written as one, not apologised for.**

`tests/deploy/test_docs_are_true.py` already ratchets over `LIVE_DOCS` and has
`test_no_live_document_asserts_the_guard_module_is_absent`. **Widen it, never shrink it** —
`test_the_live_document_list_covers_the_documents_a_judge_reads` exists precisely to stop
`LIVE_DOCS` losing a path. Add a check in the same shape: no live document may assert the demo
route is unrouted or that the endpoint 404s, since the wire says otherwise. Model it on the
falsification tests at the end of that file.

**Every number you write must be one you measured or one this plan measured** — §0 is the
record and cites how each figure was obtained. Do not copy a figure from another document
without re-deriving it; that is how §9 went stale.

Done when: no live document claims the demo route is absent or 404s; the new ratchet fails
against the pre-fix text and passes after; `LIVE_DOCS` has not lost a path.

**NO SHORTCUTS** — never weaken a ratchet or shrink `LIVE_DOCS`; never delete a test to make a
document pass. **NO DEPLOY** — never `terraform apply`, never redeploy the Lambda.
**NO SECRETS** — never write the SSM parameter, never print a DSN, never paste one into a
document or a runbook example. Report `--junitxml` counts before and after (576/575/0/0).
