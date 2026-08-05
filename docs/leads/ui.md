# UI/UX LEAD — THE CONSOLE: a surface that authenticates itself

**Domain implementation plan.** `verticals/mainline/apps/console` — one TypeScript SPA in its own
pnpm workspace (FSL-1.1-ALv2). Milestone K5 depth at ⟦H⟧, with the K4/K6 read surfaces and the
`G5` browser spec.
Authority: `ARCHITECTURE.md` §4, §5.3–5.9, §6.4–6.5, §7, §8.3, §11.4–11.6, §12, §17;
`BUILD_PLAN.md` §3–5 (K5 contents, the five beats, `G5`, `G6`), §10.2 (the cut ladder).
Consumed contracts: `spec/wire/refusal.md`, `spec/errors.md`, `spec/conformance/manifest.toml`
(kernel lead); `packages/trappoint-recall/.../views_contract.md`, `spec/wire/candidate-commitment.md`
(recall lead); `delta_witness` + `DeltaVerdict` (algorithms lead).
Nothing here re-litigates a decision those documents made. Where they leave a genuine choice, §2
rules on it in one line.

---

## 0. The problem this domain actually has

`BUILD_PLAN.md` §3/K5 contains the sharpest sentence anyone has written about this console:

> *the terminal carries claims about the database and the UI carries claims about a human decision —
> an engineer can authenticate a SQLSTATE on screen; nobody can authenticate a React component.*

That is correct, and taken literally it caps the console at three severe screens forever. The founder
requirement — *next level, 3D, ultra-innovative, one of its kind* — is not compatible with that cap,
and "add spectacle anyway" loses the room the first time a judge sees a particle system over a
fatality record.

**Both are satisfied by removing the premise.** A React component cannot be authenticated *because it
is normally a rendering of an assertion someone else made*. So the console stops being a rendering.

> **The console re-derives, in the browser, from signed bytes, every claim it displays — and shows
> the derivation.** RFC 8785 canonicalisation, RFC 6962 leaf/inclusion/consistency hashing, the
> ECDSA-P256 checkpoint signature, the PER silence-root boundary proof, and the payload digests
> behind every exposure receipt are recomputed in a Web Worker from the same bytes `trappoint-verify`
> consumes, against committed cross-verifier vectors. What the screen shows is not *the database's
> word*; it is *our arithmetic over the database's signature*, and a stranger can run the same
> arithmetic in Python.

That single decision (D6) buys the whole domain: it makes a UI claim as authenticatable as a
SQLSTATE, it makes the demo URL work with no AWS credentials (D7), it makes the visual language a
statement about evidence rather than decoration, and it makes the one dimensional surface defensible
because everything around it is provably severe.

**Deliverable at ⟦H⟧:** six surfaces (gate · ancestry · disposition · custody+audit · propagation ·
silence), the in-browser verifier, the replay player, and a deterministic browser spec that is `G5`'s
"browser spec green against the live URL" line item.

---

## 1. Strategy

### 1.1 Three registers, and the register is enforced by the import graph

Design with gravity is not a mood; it is a partition with a lint. Every component belongs to exactly
one register, declared in its directory, and the boundary is a CI-enforced dependency rule — the same
idiom the repository already uses for licence layers.

| Register | Surfaces | Law | Enforcement |
|---|---|---|---|
| **EVIDENCE** — severe | gate refusal, clause diff, disposition, custody, audit, silence | Mono for anything the database emitted verbatim. No easing over 160 ms. No depth, no parallax, no gradient, no bloom. One severity accent over a neutral ramp. Every claim carries a provenance chip. Nothing moves that a screenshot could not reproduce. | `src/features/{gate,diff,disposition,custody,audit,silence}/**` **may not import** `motion` or `@react-three/*`. ESLint `no-restricted-imports` + a unit test over the built module graph. |
| **INSTRUMENT** — mechanical | the six gate counters, the weld diagram, the reading-floor meter, propagation states | Motion is permitted only where the *transition is the fact* — a counter going 1 → 0 is the product working. Linear or single-cubic, ≤ 220 ms, always interruptible, always skipped under `prefers-reduced-motion`. | `motion` allowed; `@react-three/*` forbidden. |
| **MEMORY** — dimensional | the ancestry walk, and nothing else, ever | See §1.2. | The only directory permitted to import `@react-three/*`. |

The register is also the a11y contract: EVIDENCE surfaces must be fully operable with a screen reader
and a keyboard and must print to a court-legible page; MEMORY must be entirely optional.

### 1.2 Dimensionality earns its place exactly once — and the rule that earns it

The blame walk is the only inherently spatial-temporal object in the product: a commit DAG walked
backwards through twenty-two years and three identity-preserving reflows to a 2013 fatality. Depth
here is not ornament — **the third axis is time**, and the walk is the one thing a flat diagram
genuinely cannot show at the density the corpus has.

Four rules make it read as gravity rather than as a screensaver, and they are written into
`docs/dimensionality-charter.md` as testable statements:

1. **The stillness rule.** In the MEMORY register the severity-5 node is the only object in the scene
   that never moves, never scales, never emits and never responds to hover. Everything else moves
   past it. Stillness marks the dead; motion is for the living record. This is the design idea, and
   it is asserted by a unit test over the animation graph, not by taste.
2. **Camera on rails, constant velocity.** No easing into a fatality, no dolly zoom, no orbit. The
   walk is a walk. The user's only controls are *further back* and *further forward* along one axis,
   plus a stop.
3. **No emissive vocabulary.** No bloom, no lens flare, no god rays, no particles, no depth of field.
   Monochrome plus the single severity accent, the same token set as EVIDENCE. The 3D surface uses
   *fewer* colours than the tables, not more.
4. **No name is ever rendered in the MEMORY register.** Events carry titles and severities; people do
   not appear. This carries §11.5's Attribution Rule and I15 into pixels, where a screenshot lives
   longer than a schema.

### 1.3 The degraded 2D path is the same truth minus one axis (never a fallback)

Layout is computed **once**, deterministically, by a pure seeded function in a Web Worker
(`ancestry/layout`), producing an `AncestryLayout` — nodes with `(x, y, t)`, edges, lanes, severity
bands, truncation flags. The 2D **ribbon** (SVG) and the 3D **walk** are two renderers over one
layout. Consequences, all of them load-bearing:

- The ribbon is not a reduced version; it is the same layout projected on `(x, y)`.
- An invariant test asserts **every node and edge present in the 3D scene graph is present in the
  ribbon DOM** — so no fact is 3D-only, which is simultaneously the a11y guarantee, the print/exhibit
  guarantee and the cut-ladder guarantee.
- The ribbon is the **exhibit form**: it prints to A3 with a caption block carrying the corpus root,
  the closure generation and the `ancestry_complete` flag. A court exhibit is a PDF, not a canvas.
- `prefers-reduced-motion`, a failed WebGL2 probe, a `deviceMemory < 4`, a battery-saver signal, or
  `?render=2d` all select the ribbon. **The 3D chunk is never in the critical path** — it is a lazy
  chunk that, if it fails to load at all (including because a cut deleted it), leaves the ribbon.

### 1.4 Replay-first: the console's default transport is a signed evidence bundle

AWS credentials are not valid on the founder's machine and `G6` requires *a functional, free demo
URL*. Both are solved by the same artefact.

An **EvidenceBundle** is a content-addressed directory (`manifest.json` + `frames/` + `ledger/` +
`sql/`) produced by `scripts/capture-bundle.ts` from a real run: every HTTP exchange the console makes
is captured byte-for-byte, alongside the ledger leaves/nodes/checkpoint and the verbatim SQL round
trips already being written to `evidence/demo-run-<ts>/` by the `G5` discipline. The player mounts the
bundle behind the *same* client interface the live transport implements, so `LIVE` and `REPLAY` differ
in one line of composition and in one badge — never in a code path.

Why this is not a mock: the bundle is **verified before it is rendered**. `manifest.files[].sha256`,
the checkpoint note signature and the inclusion proofs are all checked in-browser (D6). A tampered
fixture fails to render and says why. *The console cannot show you a screen we made up*, and that is a
demonstrable property rather than a promise.

### 1.5 Red before green, in a browser

PL-2 in this domain means the **browser spec exists and is red before the surfaces do**. Ordering:
foundation → tokens + contracts → **the conformance harness with a failing `demo-walkthrough.spec.ts`
naming all six surfaces** → the surfaces, each landing with its own spec that was written red first.
`docs/console-conformance.md` is the machine-checked list; it is the artefact `G5` reads.

The two failing assertions that must be red first, because they are the only ones that assert the
product: `gate.spec.ts` asserting the refusal bar renders the string `gate_closed_when_issued` and
SQLSTATE `23514` **taken from the bundle, not from a literal in the test**; and `disposition.spec.ts`
asserting the countersigner field is present **because `clearance_legal` required it**, with the test
flipping the lattice row in the fixture and asserting the field disappears. A feature-flagged
countersigner field would pass a naive test and is exactly the lie BUILD_PLAN §3 warns about.

### 1.6 Determinism, because a demo is a capture

Cinema mode (`?cinema=1&seed=…&t=…&frame=…`) freezes `Date.now`/`performance.now`, seeds a xorshift
PRNG that every non-deterministic value must draw from, disables all transitions, and puts r3f in
`frameloop="never"` with manual `advance()`. Playwright runs at 1920×1080, `deviceScaleFactor: 1`,
`page.clock.install()`, and — for the 3D surface — ANGLE/SwiftShader software GL, which rasterises
identically across machines. Result: the ancestry walk is screenshot-testable, which almost no WebGL
surface is, and the video's most-watched seconds are reproducible from a command.

---

## 2. Decisions

| # | Decision | Why, in one line |
|---|---|---|
| **D1** | **Vite 7.1.x · React 19.2.x · TypeScript 5.9.x `strict` + `noUncheckedIndexedAccess`.** Exact pins, no carets; versions recorded in an ADR. | Vite 8 and TS 6.0 are stable but buy nothing this milestone and the r3f/drei chain is proven on 7 — PL-3 applies to build tools too. |
| **D2** | **No router library, no data-fetching library, no component library, no CSS framework.** A 60-line typed router over the surface registry, `useResource` with `AbortController`, CSS Modules + custom properties. | Six static surfaces; in a repo where the dependency graph is a licence and liability boundary, every avoided dependency is an avoided audit. |
| **D3** | **`motion` (MIT) for DOM animation. GSAP is banned.** | GSAP is free since 2025 but its Standard License is not OSI/SPDX — `reuse lint` green is a `G6` checklist item and no non-SPDX licence enters this tree. |
| **D4** | **three.js `WebGLRenderer` + `@react-three/fiber` v9 + `drei`. No WebGPU, no post-processing stack.** | WebGPU is absent or blacklisted on the fleet laptops this must run on, and PL-3 forbids an unproven capability on a dated path. |
| **D5** | **The console never computes a gate condition and never writes an evidentiary row.** It reads, it POSTs to the kernel's three procedures, and every gate-relevant number is rendered verbatim with a provenance chip (`db:column`, `db:constraint`, `recomputed`, `staged`). | If the console could compute `open_blocking`, the flagship claim would be launderable in TypeScript — P2, one hop further downstream. |
| **D6** | **The console verifies in-browser**: vendored RFC 8785 JCS (TS), SHA-256 via WebCrypto, RFC 6962 leaf/node/inclusion/consistency, C2SP checkpoint note parse + ECDSA-P256 verify, PER boundary-proof check — in a Worker, against vectors byte-identical to `trappoint-verify`. | It converts "nobody can authenticate a React component" from a true statement into a false one, which is the whole design. |
| **D7** | **Replay-first transport.** Default = a verified EvidenceBundle; live = a transport swap; a permanent non-dismissible badge says which. | Gives a real free demo URL with no AWS, makes capture reproducible, and makes the STAGED column of the honesty card mechanical rather than remembered. |
| **D8** | **Surfaces self-register** via `import.meta.glob('/src/features/*/surface.tsx')`; a missing surface renders an honest **NOT BUILT YET** card carrying the milestone that owns it. | Zero central route table ⇒ zero cross-worker file collisions, and the cut ladder becomes `rm -r` with a truthful UI consequence. |
| **D9** | **The three registers are an enforced import boundary** (§1.1), not a style guide. | A design law nobody can violate is worth more than a design law everybody agrees with. |
| **D10** | **The stillness rule** (§1.2.1) is the MEMORY register's defining constraint and is unit-tested. | It is the one idea that makes dimensionality read as respect instead of spectacle. |
| **D11** | **One layout, two renderers**, with a test asserting 3D ⊆ ribbon. | Makes the degraded path first-class by construction rather than by intention. |
| **D12** | **Cinema mode + SwiftShader + `page.clock`** for byte-stable screenshots including WebGL. | The `G5` browser spec must be able to fail; a flaky visual baseline is a spec that asserts nothing. |
| **D13** | **Budgets are tests**: evidentiary shell ≤ 220 KB gzip, lazy 3D chunk ≤ 600 KB gzip, gate surface interactive < 1.0 s at 4× CPU throttle, interaction p95 < 100 ms, first refusal paint < 400 ms from bundle. | "Sub-second on a mine-site laptop" is a number or it is marketing. |
| **D14** | **Accessibility is a gate**: axe-core zero serious/critical on all six surfaces, a complete keyboard-only path gate → disposition → signature, contrast asserted in unit tests over the token set, reduced-motion forcing the ribbon. | A safety product that a supervisor with a cracked screen and gloves cannot operate has an availability of zero regardless of uptime. |
| **D15** | **No named person is rendered in MEMORY; `signer_sub` is never a visual dimension** (never a colour, axis, facet or sort key) anywhere in the console. | I15 / the A-RULE, carried into the artefact that outlives the schema — a screenshot. |
| **D16** | **Honesty chrome** — a permanent strip carrying `LIVE`/`REPLAY`, the bundle digest prefix, the verification seal, the corpus root, and server-vs-local clock skew. | The UI's own must-not-claim control; it is also the single best five seconds of the video. |
| **D17** | **WebAuthn is a render-time switch, not a runtime branch**: the build reads `g1-attestation.json` (`GT-15`) and compiles either the WebAuthn capture path or the OIDC + signed-envelope path, and the honesty chrome names which one. | Mirrors the kernel lead's D5; an unverified capability must not reach a rendered artefact. |
| **D18** | **Refusals are rendered from `spec/wire/refusal.md` payloads only** — constraint, SQLSTATE, minimal unsatisfiable subset, nearest admissible alternative — never from a message the console composes. | I14 is a wire contract; a prettified refusal is a different refusal. |

---

## 3. Sequencing

```
        W1 console-foundation
             │
     ┌───────┴────────┐
 W2 visual-language   W3 data-contracts-replay
     └───────┬────────┘
        W4 cinema-conformance-harness   ← lands RED: demo-walkthrough.spec.ts names all six surfaces
             │
   ┌────┬────┼─────┬──────┬──────┐
  W5   W6   W8    W9     W10     │        W5 gate+diff · W6 ancestry ribbon
 gate  anc  verify disp  prop/sil │        W8 verifier+custody+audit · W9 disposition · W10 propagation+silence
        │
     W7 ancestry-walk-3d                  ← cut-ladder item 1; deleting its directory leaves the ribbon
```

Two ordering rules. **The harness is fourth, not last** — PL-2 requires the failing spec to precede
the surface. **W7 is last and isolated** — it is `BUILD_PLAN` §10.2's first cut, and nothing may
depend on it.

Calendar fit: W1–W4 are D-9→D-7 work; W5, W6, W8, W9 are the D-5 "three console screens pixel-final"
line plus the audit surface `G5` needs; W10 and W7 are the texture the ladder is allowed to take.

---

## 4. Interfaces

**Published by this domain** (other domains and the demo consume these):

| Artefact | Consumers | Owner |
|---|---|---|
| `contracts/*.schema.json` + `src/data/types.generated.ts` — the console's read model | capture script, browser spec, backend leads validating their read payloads | W3 |
| `EvidenceBundle` format — `docs/evidence-bundle.md` + `scripts/capture-bundle.ts` | demo capture, `evidence/demo-run-<ts>/`, the offline tier | W3 |
| `verifyBundle()` / `useVerification()` — TS mirror of `trappoint-verify` checks 1–4, 9–11 | custody + audit surfaces, the browser spec | W8 |
| `tests/vectors/**` — cross-verifier golden vectors | `packages/trappoint-verify` (Python) must agree byte-for-byte | W8 |
| `AncestryLayout` — deterministic layout type and worker | ribbon, 3D walk, print exhibit | W6 |
| `docs/console-conformance.md` — the `G5` browser-spec checklist | preflight warden, `just demo:preflight` | W4 |
| `SurfaceDescriptor` — the self-registration contract | every feature worker | W1 |

**Consumed from other domains** (and the fallback if it is late — no worker may block on one):

| Contract | Owner | Fallback |
|---|---|---|
| `spec/wire/refusal.md` (`{constraint, sqlstate, mus[], naa{}, subject, gate_epoch, evidence}`) | kernel W1/W8 | Ship the schema copy in `contracts/refusal.schema.json` with a CI diff against `spec/` once it lands. |
| `spec/errors.md` — the SQLSTATE contract | kernel W1 | Same. |
| `mainline_audit.v_*` column contracts | recall/MCP leads | Captured payloads in the bundle; the audit surface renders columns generically from the schema. |
| `delta_witness` rows + `DeltaVerdict` | algorithms W4 | The diff renders `control_delta` with an explicit **witness unavailable** state — never an inferred explanation. |
| `GET /v1/clauses/{uuid}/ancestry?as_of=` (read projection) | **unassigned** | `scripts/capture-bundle.ts` emits the payload directly from SQL; the console never learns the difference. |

**Hard boundaries.** No worker touches `.github/**` (the CI lead wires `pnpm -C verticals/mainline/apps/console run ci`). No worker touches `spec/**`, `packages/**` or `evidence/**`. The console workspace is its own pnpm root with its own lockfile; it never enters the uv workspace.

---

## 5. Worker roster

| # | id | One-line purpose |
|---|---|---|
| 1 | `console-foundation` | The workspace, the build, the shell, the self-registering surface contract, the capability probe, and the budget/licence gates. |
| 2 | `visual-language` | The three registers as executable tokens and primitives, the import-boundary lint, and contrast/reduced-motion as unit tests. |
| 3 | `data-contracts-replay` | The read-model contracts, the generated types, the transport, and the verified EvidenceBundle format + capture script + fixtures. |
| 4 | `cinema-conformance-harness` | Deterministic cinema mode, the Playwright harness with stable WebGL screenshots, the a11y and budget gates, and the **red** composite demo spec. |
| 5 | `gate-refusal-screen` | The money screen: the refusal bar with its constraint name and SQLSTATE, the MUS/NAA panel, the six-counter weld diagram, and the clause diff that armed the check. |
| 6 | `ancestry-layout-ribbon` | The deterministic layout engine and the 2D ribbon — the default, accessible, printable exhibit form of the blame walk. |
| 7 | `ancestry-walk-3d` | The one dimensional surface: a rails-camera walk back through time under the stillness rule, lazy, deletable, and screenshot-tested. |
| 8 | `verifier-custody-room` | The in-browser RFC 8785/6962/ECDSA verifier plus the custody-chain and MCP-audit surfaces it certifies. |
| 9 | `disposition-lattice-modal` | The screen that shows a person being made to sign: lattice-driven fields, per-check defeater vocabulary, reading-floor meter, WebAuthn/OIDC capture. |
| 10 | `propagation-silence-ledger` | Where a lesson travelled, where it did not, and everything the system declined to surface with its arithmetic. |

---

## 6. Risks accepted, and what happens

1. **The 3D walk is the first thing the ladder cuts.** Accepted by isolating it in one directory with
   one lazy import and a test proving the ribbon carries every fact. Cost of the cut: texture, not a
   claim. *This is the intended outcome if D-7 preflight is not green.*
2. **WebGL screenshot stability may still be imperfect on SwiftShader.** Pre-committed fallback: the
   ancestry-walk spec drops to DOM/scene-graph assertions plus a non-blocking visual diff, and
   `docs/console-conformance.md` records that the 3D surface has no pixel baseline. No spec is
   allowed to become advisory silently.
3. **`GT-15` may forbid WebAuthn.** D17 makes it a compile-time selection; the OIDC + signed-envelope
   path is built in the same worker, not discovered on D-4.
4. **The ancestry read endpoint has no owner.** Mitigated by the capture script sourcing it from SQL.
   If it is never built, the console is replay-only for that surface and the honesty chrome says so.
5. **The verifier could disagree with `trappoint-verify`.** That is the point, and it is a CI failure
   on either side; the vectors are committed and both implementations must move together.
6. **Six surfaces at K5 depth is more than the "three pixel-final screens" the plan budgets.** Three
   are pixel-final (gate, ancestry, disposition); custody, audit, propagation and silence are severe
   tables with a verification seal — cheap by construction, and cuttable to a terminal tape.
7. **A judge may still read any 3D as unserious.** The mitigation is structural: the first five
   seconds of the console are the honesty chrome and a refusal in mono, and the walk is reachable only
   after a refusal has been shown. Spectacle never precedes evidence.
8. **The console is one person's taste until someone else sees it.** No mitigation beyond the
   register lint and the a11y gate; recorded as a known unmeasured risk.

---

## 7. What this domain will not build

No dashboards, no charts of people, no "AI assistant" panel, no drag-and-drop workflow builder, no
notification centre, no dark-pattern confirmation, no animation that survives `prefers-reduced-motion`,
no cloud-console screenshot anywhere (trademark-dense — never filmed), and no screen that can be
reached without the honesty chrome. The absence is the point, exactly as it is for the kernel's six
endpoints.

---

*UI/UX lead plan. One SPA, three registers, one dimensional surface with a stillness rule, a verifier
in the browser that makes a React component as authenticatable as a SQLSTATE, and a browser spec that
was red before any of it existed.*
