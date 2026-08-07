<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# MAINLINE console

> *the terminal carries claims about the database and the UI carries claims about a human decision —
> an engineer can authenticate a SQLSTATE on screen; nobody can authenticate a React component.*
> — `BUILD_PLAN.md` §3, K5

That sentence is true of a console that **renders assertions somebody else made**. This one is being
built so that it stops being true: it re-derives, in the browser, from signed bytes, every claim it
displays — and shows the derivation (`docs/leads/ui.md` D6).

This directory is the foundation for that: the workspace, the build, the shell, the self-registering
surface contract, the capability probe, and the two gates that keep the whole thing honest. **No
feature surface lives here.** Nine other workers add those, one directory each.

---

## Run it

```sh
pnpm install          # its own lockfile; never joins the repo's uv workspace
pnpm run dev          # http://localhost:5173
pnpm run ci           # lint · typecheck · unit tests · build · budgets · licences
```

`pnpm run ci` is the whole gate and it must exit 0. It needs no cloud account, no database, no model
call and no network beyond the install.

| Script | What it does |
|---|---|
| `dev` | Vite dev server, port 5173, strict |
| `build` | typecheck both projects, then `vite build` (writes `dist/.vite/manifest.json`) |
| `preview` | serve `dist/` on 4173 |
| `test` / `test:watch` | Vitest, jsdom, `tests/unit/**` |
| `test:browser` | Playwright. Config and specs are owned by `cinema-conformance-harness`; `@playwright/test` is already installed. |
| `lint` | ESLint, `--max-warnings 0`, including the **register import boundary** |
| `typecheck` | `tsc --noEmit` over `tsconfig.json` and `tsconfig.node.json` |
| `check:budgets` | D13. Reads the build manifest, gzips the real closure, fails on `budgets.json` |
| `check:licences` | Walks the installed dependency graph, fails on a licence outside the allowlist |

---

## What a feature worker has to do (D8)

Add **exactly one file**: `src/features/<id>/surface.tsx`, exporting `surface`.

```tsx
// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2
import type { SurfaceDescriptor } from '../../app/surfaces';
import { GateScreen } from './GateScreen';

export const surface: SurfaceDescriptor = {
  id: 'gate',                     // MUST equal the directory name
  path: '/gate',                  // reachable at #/gate
  title: 'Gate — the refusal',
  register: 'evidence',           // 'evidence' | 'instrument' | 'memory'
  order: 10,
  milestone: 'K5',
  Component: GateScreen,
};
```

There is no route table to edit and no registry to append to — `import.meta.glob` finds it. Two
things follow:

- **A surface that does not exist renders a NOT-BUILT-YET card** naming the milestone, the owning
  worker, the path it was expected at, and what the screen owes the reader. Deleting a feature
  directory (the scope-cut ladder, `BUILD_PLAN.md` §10.2) therefore produces a *truthful* UI
  consequence rather than a hole.
- **A surface that lies about itself is treated as a surface that is not there.** Wrong `id`, unknown
  `register`, non-callable `Component`, or a chunk that fails to fetch — each produces the same card
  carrying the exact reason, verbatim. `SurfaceHost` has four outcomes and all four paint. A blank
  pane is not one of them.

The console's list of promises lives in `DECLARED_SURFACES` (`src/app/surfaces.ts`). It cannot make a
surface exist; it exists so that an **absence is nameable**.

### Filling the honesty chrome (D16)

The strip at the top is permanent, has no dismiss control, and starts by admitting it knows nothing.
Every slot renders `unknown` with a loud `unset` provenance marker until the worker who can actually
establish the fact publishes it:

```tsx
import { useHonestyPublisher } from '../../app/honesty';

const publish = useHonestyPublisher();
publish({ transport: 'replay', bundleDigestPrefix: '1f3ba90c4d2e', seal: 'verified' });
```

Outside a provider the publisher is a no-op and the reader is `UNKNOWN_HONESTY`, so nothing has to
guard. **Do not add a slot whose default state is reassuring.** An unfilled slot must look unfilled.

### Choosing a renderer (`src/app/capability.ts`)

```ts
import { CAPABILITY } from '../../app/capability';
CAPABILITY.renderMode;   // '2d' | '3d'
CAPABILITY.reasons;      // the arithmetic, in order, safe to render verbatim
```

Frozen, computed once at module load. Two rules it enforces that a careless probe gets wrong:
an **unreported** `deviceMemory` is `null` and `null` is not "low"; and `?render=3d` is a *request*
that a missing WebGL2 context refuses, with the refusal recorded in `reasons`.

---

## The three registers are an import boundary, not a style guide (D9)

`eslint.config.js` enforces `docs/leads/ui.md` §1.1 mechanically:

| Register | Directories | May import |
|---|---|---|
| **EVIDENCE** | `src/app`, `src/data`, `src/verify`, `features/{gate,diff,disposition,custody,audit,silence}`, `features/ancestry/{,layout,ribbon,exhibit}` | neither motion nor 3D |
| **INSTRUMENT** | `features/propagation`, `src/design` | `motion` — not 3D |
| **MEMORY** | `features/ancestry/render3d` **only** | 3D |

Banned everywhere, in every register: **GSAP** (D3 — free since 2025, but its Standard License is not
OSI-approved and has no SPDX identifier), plus every router, data-fetching, component and CSS-framework
library D2 rules out.

> **A note on how this rule was verified.** The first version expressed the denials as
> `no-restricted-imports` **`paths`** entries including `'motion/*'`. A probe file importing
> `motion/react` passed clean: `paths` entries are matched as *exact strings*, so `'motion/*'`
> refused a module literally named `motion/*` and permitted the import anybody would actually write.
> The denials are now `patterns` groups, and the probe refuses both `three` and `motion/react`. A
> boundary that reads as enforced and is not is worse than no boundary — which is why the lint is
> only half of D9, and a unit test over the built module graph (owned by `visual-language`) is the
> other half.

---

## The two gates

### `check-budgets.ts` — D13, budgets are tests

Reads `dist/.vite/manifest.json`, walks each budget's real static-import closure, gzips the emitted
bytes at level 9, and fails on the thresholds in `budgets.json`:

| Budget | Threshold | Required |
|---|---|---|
| `evidentiary-shell` — entry chunk + static closure + CSS | 220 KB gzip | yes |
| `memory-register-walk` — the lazy 3D chunk | 600 KB gzip | **no** — its absence is legal (cut 1) |

It also enforces the **lazy boundary**: no MEMORY-register library may be bundled into the entry
chunk. The manifest cannot answer that question — three.js has no manifest key, it is bundled *into*
a chunk — so the check reads each entry-closure chunk's **sourcemap `sources`**, which is the complete
list of modules Rollup folded in. If a sourcemap is missing, the check **fails**: a boundary check
that cannot see the module graph has not passed, it has not run.

Verified by construction: a probe that statically imported `three` from `src/main.tsx` raised the
shell from 68.9 KB to 85.8 KB and produced
`[lazy-boundary] "three" is bundled INTO the evidentiary entry chunk`.

### `check-licences.ts` — the dependency graph is a liability boundary

Walks the installed tree from `package.json`'s own roots. No external process, no network: the same
verdict offline as in CI. Three refusals — a **denied name** (GSAP, regardless of what its licence
field says), a **licence outside the allowlist**, and a package that **will not say what it is**.

The runtime closure (what actually ships) gets the strict permissive set. The dev closure gets that
set plus a short itemised extension — currently `MPL-2.0` (axe-core, file-level copyleft, never
linked into the distributed bundle) and attribution-only Creative Commons on tooling assets. Each
extension carries its reason in the source. `EXCEPTIONS` is deliberately empty; adding one is a
visible diff in a file whose purpose is to be read during an audit.

A **second, weaker evidence tier** exists for packages that ship a clear licence file and omit the
`license` field — `webgl-constants`, reached through `@react-three/drei → detect-gpu`, is one today.
Those are admitted and then **reported separately**, because a licence recognised from prose is
weaker evidence than a declared SPDX identifier and must not be folded silently into a pass.

---

## Decisions this directory implements, and why

| | |
|---|---|
| **Exact version pins, no carets** | D1. `vite 7.1.12 · react 19.2.8 · typescript 5.9.3 · vitest 3.2.7`, and everything else. Vite 8 and TypeScript 7 exist and buy nothing this milestone. |
| **No router, no data-fetching library, no component library, no CSS framework** | D2. `src/app/router.ts` is ~60 lines. Six static surfaces do not need more, and every avoided dependency is an avoided audit. |
| **Hash routing** | The built console must deep-link from a bare static host, from an arbitrary sub-path, and from `file://`. The offline reproduction tier is on `BUILD_PLAN` §5's never-cut list and a history-API router needs a rewrite rule a `file://` URL cannot have. `base: './'` for the same reason. |
| **The signature path is a build-time switch** | D17. `vite.config.ts` reads the GT-15 attestation and compiles either the WebAuthn or the OIDC + signed-envelope capture path. **Absent attestation ⇒ `unknown`, and the chrome says so** — never a silent default to the capability we would prefer. A *malformed* attestation fails the build, because that means somebody produced the file and it does not parse. |
| **The shell composes no evidentiary claim** | D5. It renders the chrome, the navigation and one surface. `no-console` is an error (`console.error`/`warn` excepted) because an accidental composed claim gets screenshotted. |
| **The error boundary never swallows a message** | A refusal renders its constraint, SQLSTATE and the database's message verbatim (D18/I14), and flags a SQLSTATE outside `spec/errors.md` §1's closed set as a **defect, not an edge case**. Anything else renders the exception's own name, message and stack. "Something went wrong" appears nowhere. |
| **Node 24 runs the gate scripts directly** | `node scripts/check-budgets.ts`. Built-in type stripping, no bundler in the gate path — which is why `erasableSyntaxOnly` is on in both TypeScript projects. |

---

## Red before green (PL-2)

For a product whose deliverable is a refusal, a test suite that has never been red asserts nothing.
`tests/unit/app/registry.test.ts` and `capability.test.ts` were written and observed failing before
`src/app/surfaces.ts` and `capability.ts` existed. They were then checked by mutation — the two
assertions that carry the product were each made to fail by a one-line change to the implementation
and restored:

| Mutation | Assertion that went red |
|---|---|
| `deviceMemoryGb: host.deviceMemoryGb ?? 2` | *reports an unreported deviceMemory as null and does NOT infer one* — `expected 2 to be null` |
| `buildRegistry` filters out surfaces with no module | *marks every declared surface missing when no feature module exists* — `expected [] to have a length of 7` |

Both gates were checked the same way: a fabricated `gsap` and a `GPL-3.0-only` package were each
refused by name and by licence, and a statically imported `three` was caught at the lazy boundary.

---

## Layout

```
├── index.html                 pre-boot notice + an honest <noscript>; no external origin, anywhere
├── budgets.json               the D13 thresholds
├── eslint.config.js           the register import boundary (D9) + the D2/D3 bans
├── src/
│   ├── main.tsx               mounts; removes the pre-boot notice only once React is about to render
│   ├── env.d.ts               build-time constants
│   └── app/
│       ├── surfaces.ts        SurfaceDescriptor, DECLARED_SURFACES, the glob registry
│       ├── router.ts          hash router, ~60 lines, typed
│       ├── capability.ts      the frozen probe
│       ├── honesty.ts         the chrome's state, context and hooks
│       ├── HonestyProvider.tsx
│       ├── HonestyChrome.tsx  permanent, non-dismissible, unset-by-default
│       ├── SurfaceHost.tsx    four outcomes, all of which paint
│       ├── NotBuiltYet.tsx    the honest absence card
│       ├── ErrorBoundary.tsx  refusal-aware; never swallows a message
│       ├── tokens-fallback.css  zero-specificity :where() fallbacks; src/design/ overrides them
│       ├── chrome.module.css
│       └── shell.module.css
├── scripts/                   the two gates (run by `node`, no bundler)
└── tests/
    ├── setup.ts               jsdom shims only — never a stub that makes a test pass
    └── unit/app/
```

`src/design/` is imported through a glob that evaluates to `{}` when the directory is absent, so the
shell builds before the visual-language worker lands anything and survives that directory being cut.

---

## Known limits, stated rather than discovered later

1. **`test:browser` has no config yet.** `@playwright/test`, `@axe-core/playwright` and `axe-core` are
   installed and licence-audited; `playwright.config.ts` and the specs belong to
   `cinema-conformance-harness`. `pnpm run ci` deliberately does not run them.
2. **No `WebWorker` lib in the TypeScript config.** `DOM` and `WebWorker` conflict in one program.
   The in-browser verifier (D6) will need its own narrow tsconfig or a
   `self as unknown as DedicatedWorkerGlobalScope` cast at its entry.
3. **No Content-Security-Policy meta tag.** A CSP strict enough to matter breaks the dev server's
   eval; it belongs on the serving layer, where it can differ between dev and the demo URL. Not
   claiming a protection that is not there.
4. **`noPropertyAccessFromIndexSignature` is off in the app project** and on in the tooling project.
   `vite/client` types a CSS Module as `{ readonly [k: string]: string }`, so the flag would force
   `styles['failureTitle']` on every className in the workspace — a real cost paid by ten workers for
   no safety, since a missing class name is a styling defect and never an evidentiary one.
5. **The attestation path is a guess until the platform domain lands one.** `vite.config.ts` looks in
   `evidence/attestations/g1-attestation.json` and `evidence/g1-attestation.json`, and honours
   `MAINLINE_ATTESTATION`. If the real location differs, the constant to change is in one function.
