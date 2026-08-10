<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Building the console for the demo URL

**Owner:** `w8-console-composition`.
**Artefact:** `verticals/mainline/apps/console/dist/` — the whole demo site, static files only.
**Consumed by:** `w5-tf-site` (the S3 bucket behind CloudFront) and `w7-env-and-deploy`
(the one-command deploy).
**Measured:** 2026-08-10, node v24.14.0, pnpm 11.5.3, on this machine. Every number below
was produced by a command in this document.

---

## 1. The command

```bash
cd verticals/mainline/apps/console
pnpm install --frozen-lockfile          # once; node_modules is already present here
MAINLINE_BUILD_ID="$(git rev-parse --short HEAD)" \
  pnpm exec vite build --mode demo
```

`--mode demo` makes Vite read `.env.demo`, which is committed beside `package.json` and
is annotated line by line. That file builds **Phase 1**: a console over a
cryptographically verified EvidenceBundle, with no API and no database in the request
path. `docs/leads/deploy-plan.md` §4 is explicit about why that is the default —
*"Nobody is allowed to let the live path hold the URL hostage."*

**Phase 2** adds the live API by supplying one variable in the ENVIRONMENT, which Vite
applies after every `.env` file, so a deploy never edits a committed file:

```bash
VITE_MAINLINE_API_BASE=/ MAINLINE_BUILD_ID=… pnpm exec vite build --mode demo
```

> **Measured hazard — do not run that line in Git Bash on Windows.** MSYS path
> conversion rewrites a bare `/` into the MSYS root, and the value compiled into the
> artefact becomes `C:/Program Files/Git/`. Observed on 2026-08-10:
> `VITE_MAINLINE_API_BASE:"C:/Program Files/Git/"` in `dist/assets/index-*.js`. Use
> PowerShell — `$env:VITE_MAINLINE_API_BASE='/'` — or prefix the bash line with
> `MSYS_NO_PATHCONV=1`. **Always verify the compiled value**:
>
> ```bash
> grep -o 'VITE_MAINLINE_API_BASE:"[^"]*"' dist/assets/index-*.js
> ```

`/` and not a hostname, because the console and the API are served from **one** CloudFront
distribution (deploy-plan §2.1): `/v1/…` resolves against whatever origin the page was
loaded from, there is no CORS anywhere, and the built artefact names no domain — so the
same `dist/` works behind any distribution, including one created after the build.

### What each variable does

| Variable | Read by | Effect |
|---|---|---|
| `VITE_MAINLINE_BUNDLE_URL` | `src/app/source-select.ts` | REPLAY source. `./bundle/`, relative; `src/app/composition.tsx` resolves it against `document.baseURI`, so the site works from a bucket root, a sub-path and `file://`. |
| `VITE_MAINLINE_API_BASE` | `src/app/source-select.ts` | LIVE source. Empty ⇒ unset ⇒ this build has no live source. |
| `VITE_MAINLINE_LOG_VKEY` | `src/verify/config.ts` | The checkpoint trust anchor. Unset ⇒ the signature check is a **named SKIP**, the seal is amber, and the chrome says so. File digests are still recomputed and a mismatch still refuses to render. |
| `VITE_MAINLINE_CANON_SHA256` | `src/verify/config.ts` | Pins the canonicaliser; unset ⇒ ledger check 10 SKIPs. |
| `MAINLINE_BUILD_ID` | `vite.config.ts` `define` | The `build` cell of the honesty chrome. A screenshot must name the artefact it came from. |

Both variables set ⇒ the console starts **LIVE** and renders a control that switches to
**REPLAY**. One set ⇒ that one, and no control. Neither ⇒ nothing is constructed and every
surface keeps its own NO SOURCE panel, unchanged.

### Then upload

```
dist/                       → s3://mainline-demo-site/           (the console)
evidence bundle (w9)        → s3://mainline-demo-site/bundle/    (must match VITE_MAINLINE_BUNDLE_URL)
```

The bundle directory is **not** produced by this build. `w9-evidence-bundle` produces it;
this build only compiles the path at which the console will look for it.

---

## 2. What comes out — measured, 2026-08-10

```
dist bytes: 3 380 488  (3.2 MB)      49 files
  sourcemaps: 2 580 278  (2.5 MB)    18 files
  everything else: 800 210 (781 KB)  31 files
```

| Chunk | Purpose |
|---|---|
| `assets/index-*.js` | the evidentiary shell: router, honesty chrome, composition root, both transports, the contract registry, the in-browser verifier |
| `assets/DemoDriver-*.js` | **10 594 bytes** — the four demo controls, a lazy chunk, loaded only on `#/gate` |
| `assets/surface-*.js` × 7 | one per feature surface, lazy (`src/app/surfaces.ts`'s glob) |

`scripts/check-budgets.ts`, which is the gate (D13 — budgets are tests):

```
  manifest: 20 chunks
  PASS  evidentiary-shell          124.6 KB gzip  /   220 KB  (57%, 2 files)
  lazy boundary: 63 modules inside the entry closure
```

### The entry chunk grew, and by how much

| | before this worker | after |
|---|---|---|
| evidentiary shell, gzip | **70.1 KB** (32 % of budget) | **124.6 KB** (57 %) |
| modules in the entry closure | 22 | 63 |

The +54.5 KB is `src/data/contracts.ts` (seventeen JSON Schema documents, previously a
lazy `contracts-*.js` chunk because only feature surfaces imported it) and `src/verify/**`
(RFC 8785, RFC 6962, ECDSA P-256, the ledger and boundary checks). Both are now on the
critical path because the composition root constructs a transport before any surface
loads, and **both transports validate every response against its contract** while the
replay transport **cannot serve a frame before verification resolves**.

That cost is accepted rather than optimised away, and the reason is not budget headroom:
a lazily-loaded verifier is one more thing that can fail to load between the bytes and the
seal, and on the Phase-1 demo the verifier *is* the product. The number is recorded here
so the next person to look at the budget knows what moved and why.

### Sourcemaps ship. Here is the argument.

`vite.config.ts` sets `sourcemap: true` and this build keeps it, deliberately.

1. **They are the claim.** The console's central assertion (D6) is that it re-derives
   every claim in the browser and shows the derivation. A judge who opens devtools can
   read the actual RFC 6962 hashing that produced the seal, and diff it against the
   repository they were told to clone. Stripping the maps would leave *"trust our
   minifier"* exactly where the product says *"check it yourself."*
2. **They cost nothing to serve.** 2.5 MB in S3 Standard, ap-southeast-1, is
   ≈ **USD 0.00006/month**. A `.map` is fetched only when devtools is open, so no judge,
   and no page load, pays for one.
3. **They are never on the critical path.** The 124.6 KB gzip budget is JavaScript and
   CSS; the maps are outside it by construction, which is why the number above did not
   move when they were added.
4. **They leak nothing.** `import.meta.env` is inlined into the JavaScript whether or not
   a map exists, the build carries no credential (the DSN lives in SSM and only the Lambda
   reads it), and the repository must be **public** to satisfy the hackathon's Stage One
   rules anyway. There is no secret for a map to reveal that a `grep` of `dist/` would not.

If a future build must drop them, `sourcemap: false` in `vite.config.ts` is the one-line
change — and `vite.config.ts` belongs to the UI domain, not to this one.

---

## 3. The composition root, in one paragraph

`src/app/composition.tsx` is the only place in the console that constructs a transport.
Every `src/features/<id>/transport-context.ts` defaults to `null` and renders an honest NO
SOURCE panel; this module is what fills them, and it fills all six with **one** object, so
there is one cache, one clock and one verification state. D7's property — *`LIVE` and
`REPLAY` differ in one line of composition and in one badge, never in a code path* — is
kept by `buildTransport`, which is one `if`, two constructors and the same
`MainlineTransport` returned either way. The badge is read from
`transport.describe().mode`, off the object holding the bytes, never from the build-time
selection beside it: two places for one fact is one place for them to disagree.

In REPLAY the root injects the real in-browser verifier and drives it before any surface
asks for a frame. There is no permissive default, no `?skip_verification`, and no null
case — `BundleTransportOptions.verifier` is required. A bundle that does not verify
produces a panel, not a screen.

---

## 4. Verified in a browser, against a real database

Not asserted — run, on 2026-08-10, with the built `dist/` and a single local origin
serving `dist/` plus `/v1/*` through the real Lambda handler
(`mainline_demo_api.app.handler`) against CockroachDB CCL **v26.2.5** on the local node.
That is the same two-behaviours-one-origin shape CloudFront gives the deployed demo, so
there was no CORS to paper over.

**LIVE** — `VITE_MAINLINE_API_BASE=http://127.0.0.1:8787`, `#/gate?permit=aee27ab8-…`:

```
honesty chrome   transport = LIVE      clock skew = −191 ms   seal = NOT VERIFIED
source chrome    LIVE   http://127.0.0.1:8787   [switch to REPLAY]
gate surface     the permit, its seven projected counters and the CHECK that reads each,
                 every value carrying a db:column provenance chip
```

The clock skew is the proof that this was an exchange rather than a render: it is
`server_date − Date.now()`, and only a payload can supply the first half.

**REPLAY** — `VITE_MAINLINE_BUNDLE_URL=./bundle/` only, the bundle staged into
`dist/bundle/`:

```
honesty chrome   transport = REPLAY   seal = VERIFIED IN THIS BROWSER   bundle = 4ab2e066046e
source chrome    REPLAY   ./bundle/   (no switch — this build carries one source)
verifier         21 file digest(s) recomputed in this browser and all matched;
                 1 check(s) were NOT RUN and are listed below.
                 ledger/checkpoint-000005.note  skip:checkpoint-signature —
                 no verification key is configured
press POST /v1/permits/018f3a2f-…/merge  →  23514   gate_closed_when_issued
```

Both `data-sqlstate="23514"` and `data-constraint="gate_closed_when_issued"` were read out
of the live DOM, and the screen simultaneously carried the STAGED badge declaring the
fixture bundle hand-authored — the honesty machinery working on the same screen as the
claim.

**Switching** — with both variables set, one click moved the badge LIVE → REPLAY and back,
the surface node below it was never remounted, and the seal was withdrawn on the way back
rather than left reading `VERIFICATION FAILED` beside live bytes.

**The failure path** — with `./bundle/` absent, the reader gets:

```
verification failed — no frame was served
manifest is not JSON: SyntaxError: Unexpected token '<', "<!doctype "... is not valid JSON
```

which is the correct diagnosis of an SPA host answering a missing bundle with `index.html`,
and no surface below it was given a frame.

---

## 5. CI

`pnpm run ci` = `lint && typecheck && test && vite build && check:budgets && check:licences`.

**It had never been invoked before today.** It was expected to be red; it was not. Both
runs, before and after this worker's changes:

| | before | after |
|---|---|---|
| `eslint . --max-warnings 0` | clean | clean |
| `tsc` × 2 projects | clean | clean |
| vitest | 78 files, **1438** tests, all passing | 79 files, **1461** tests, all passing |
| `vite build` | ✓ | ✓ |
| `check:budgets` | PASS 70.1 KB / 220 KB | PASS 124.6 KB / 220 KB |
| `check:licences` | 372 audited, 12 licences, all permissive | unchanged |

`tests/unit/app/composition.test.tsx` (23 of the 23 added) asserts the four properties the
composition root exists to have: nothing is constructed when nothing is configured; one
live transport reaches all six surface contexts; a bundle whose verifier rejects serves no
frame and renders a failure state; and switching changes the badge and nothing else —
asserted by **DOM node identity**, so a switch that quietly remounted the surface would
fail.

---

## 6. Known gaps — what this build does not yet do

* **`POST /v1/demo/gate-run` is not addressable from the console.** The four-beat driver
  is written, styled, tested and mounted, and on the running console it renders an
  actionable absence naming the three files that must declare the endpoint — none of which
  this worker owns:
  `src/data/resources.ts` (a seventeenth `declare()`), `src/data/contracts.ts`
  (`gate-run.schema.json` registered, as a verbatim copy of the demo-api's), and
  `verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py`
  (`Route("POST", "/v1/demo/gate-run", "demo_gate_run")` plus a `SCHEMA_IDS` entry).
  `docs/deploy/gate-run-contract.md` §9 records the same three from the other side.
  Until they land, the three beats are reachable in the demo only through the gate
  surface's own single merge attempt — which does render `23514` /
  `gate_closed_when_issued` verbatim (§4), but not the projection-drift attack or the
  admission, because those need a savepoint a browser cannot hold.
* **The demo subject is write-protected (`423`).** `gate-run-contract.md` §7 states that a
  mutating transition aimed at the seeded demo permit is refused, so one judge cannot brick
  the demo for the next. If that holds as written, the deployed LIVE console's merge
  control answers `423` with a plain error body, which the transport classifies as a
  `status` failure and the surface renders as one — correct, and not a refusal. **This is
  the reason the LIVE demo is not yet the full three beats.** It is *not verified here*:
  the only migrated database on this machine belongs to another worker's fixture and this
  session made GET requests exclusively, because a POST would have mutated it. Whoever
  seeds the demo subject should press the control once and record what comes back.
* **`.env.demo.local` is not ignored by git.** The root `.gitignore` has `.env`, which
  does not match `.env.demo.local`. This document deliberately routes Phase 2 through an
  environment variable instead, so no `.local` file is needed — but if one is ever
  created, `.gitignore` needs a line. Not this worker's file.
* **No Playwright spec covers the composition root.** `tests/browser/gate.spec.ts` and its
  siblings belong to the cinema-conformance-harness worker. The browser evidence in §4 is
  a measured session, not a spec that will re-run in CI.
* **Sourcemaps are shipped** (§2). Stated here because it is a decision, not an oversight.
