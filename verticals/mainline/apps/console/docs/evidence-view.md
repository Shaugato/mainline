<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The evidence view

**The screen on which the console audits its own inputs.** Source: `src/features/evidence/`.
Tests: `tests/unit/evidence/` (81). Address: `#/evidence`.

Every other surface in this console renders a claim about a permit, a clause or a ledger. This
one renders a claim about *the console*:

> Every byte on every other screen came from a file in the table below, and this browser
> recomputed the SHA-256 of each one against the digest `manifest.json` declares.

It is the surface that makes `docs/leads/ui.md` **D6** checkable rather than asserted. A reader
with `sha256sum` and the same directory reproduces every number on the page. That is the entire
design: not *trust the screen*, but *here is the arithmetic, and here is how to repeat it
without us*.

---

## 1. Why this exists

`BUILD_PLAN` §3/K5: *an engineer can authenticate a SQLSTATE on screen; nobody can authenticate
a React component.* D6 removes the premise by having the console re-derive what it displays. But
re-derivation needs a place where the derivation is **shown** rather than merely performed —
otherwise "we verified it" is one more unauthenticatable sentence rendered by a React component.

Three concrete gaps this closes.

1. **The transport had no shipped verifier.** `BundleTransport` refuses to serve a single frame
   until an injected `BundleVerifier` returns `verified`, and it deliberately ships no default
   (`docs/evidence-bundle.md` §12: *the verifier that gates the transport is injected and is
   another worker's*; the only real one lived in the test tree). `manifestIntegrityVerifier()`
   here is a shipped one, built on the same loop this screen displays.
2. **The manifest's own digest was computed nowhere in the application.** The honesty chrome has
   a `bundleDigestPrefix` slot (D16) and nothing filled it.
3. **The coverage of the bundle was unstated.** Which declared resources have a captured
   exchange, and which do not, was a fact in nobody's head and on nobody's screen.

---

## 2. What it establishes

Exactly one thing, and it is narrow on purpose:

> **Are these the bytes that were sealed?**

For every entry in `manifest.files`: read the bytes through the source, hash them with WebCrypto
SHA-256, compare to the declared digest and the declared byte length. Plus five structural checks
that need no cryptography:

| check | what it catches |
|---|---|
| `manifest-digest` | the bytes are not the bytes that were sealed |
| `manifest-byte-length` | the digest matched but the declared length did not — the manifest contradicts itself |
| `file-present` | the manifest lists a file the source does not have |
| `manifest-lists-itself` | a manifest asserting its own digest, which no reader can check |
| `manifest-duplicate-path` | two digests for one path: a contradiction, not a duplicate |
| `frame-name-undecodable` | a file under `frames/` that no request can ever address |
| `frame-name-non-canonical` | a frame filed under a name the producer could not have written |
| `unlisted-file` | a file in the directory that nothing has checked (only when the source can enumerate itself) |
| `coverage-conservation` | the audit's own bookkeeping does not balance |

Any finding ⇒ verdict `failed`. No finding ⇒ verdict `verified`.

### 2.1 What it does NOT establish

Rendered on the screen itself, from `LIMITS` in `model.ts`, so it cannot be quietly deleted:

- **A matching digest establishes provenance, not truth.** These are the bytes that were sealed.
  Whether the numbers inside describe a real cluster is what `staged` and
  `cluster_fingerprint.source` are for — and on the committed fixture both say no.
- **Nothing here signs the manifest.** `manifest.json` is the one file whose digest is not inside
  itself. Its authenticity rests on where you fetched it from. The screen recomputes its digest
  so you can compare it against a value obtained by another route; it cannot do that comparison
  for you.
- **The carried custody bundle is not verified here.** `ledger/bundle.json` and the checkpoint
  note are `spec/wire/evidence-bundle.md` artefacts carried verbatim. Their Merkle arithmetic and
  ECDSA signature belong to the custody surface and to `trappoint-verify`. Here they are two more
  files with two more digests.
- **Absence of a smuggled file is not established** unless the source can enumerate itself. A
  static host answers requests; it does not list directories. `Coverage.unlisted` is `null` in
  that case and the screen says *not established*, never *none*.
- **One algorithm, named.** SHA-256 over the sealed bytes. Not RFC 8785 canonicalisation, not an
  RFC 6962 inclusion proof, not a checkpoint signature.

---

## 3. The four states the screen can be in

| state | when | what it renders |
|---|---|---|
| **no bundle** | `resolveBundleLocation()` found nothing, or refused what the address named | the reason, verbatim. Which of the several possible nothings this is. |
| **not checked** | there is a bundle but `crypto.subtle` is absent — an insecure origin | `VerificationSeal state="unverified"` with the reason. **Never `failed`**: an insecure origin has not accused the bundle of anything. |
| **unusable** | the manifest is missing, is not JSON, is not UTF-8, or does not satisfy `bundle.schema.json` | the failure verbatim, and the note that the transport refuses the same bundle before serving anything — so this screen is where a reader finds out why nothing else renders. |
| **audited** | the loop completed | identity, seal, coverage, inventory, findings, gaps, limits. The verdict may still be `failed`. |

There is no fifth state, and in particular no state that carries a partial inventory beside an
error. A half-table looks like a finding.

---

## 4. Where the bundle comes from

`resolveBundleLocation(params, env)` — a pure function of a query string and the build
environment.

1. `?bundle=<relative-path>` in the page's address (either query position; the hash wins, matching
   `src/app/router.ts`).
2. `VITE_MAINLINE_BUNDLE_URL`, compiled into the artefact.
3. Otherwise: nothing, and the reason says so.

**A URL parameter may name only a same-origin relative path.** Absolute URLs, protocol-relative
`//host` forms and `..` segments are refused *by name*, with the reason rendered. A link is
something a stranger can send; a console that fetched, hashed and rendered an arbitrary
cross-origin directory because a query string said so would be a machine for producing
authentic-looking screenshots of somebody else's bytes under our chrome. The build-time default
may be absolute, because whoever set it built the artefact.

---

## 5. One implementation, two consumers

`auditFiles()` is the loop. Two things wrap it:

- `auditBundle()` — for this screen.
- `manifestIntegrityVerifier(oracle)` — a `BundleVerifier` for the **composition root** to inject
  into `BundleTransport`.

So the transport's gate and the inventory on this screen are the *same arithmetic*. A bundle that
renders here as clean is a bundle the transport will play; a bundle that fails here cannot be
played at all. Two implementations could drift; one cannot. `audit.test.ts` asserts both
directions, including that a single flipped hex digit makes the transport refuse a frame whose
own digest was never touched.

**`src/data/` must never import this module.** The transport is deliberately verifier-agnostic and
ships no default; a data layer that reached into a feature directory for its verifier would invert
the dependency and make the "no default verifier" rule editable from the wrong place. The wiring
belongs in whatever composes the application — today, nothing does, and the console has no live
transport at all.

When `src/verify/` (worker `ui/verifier-custody-room`) lands the full RFC 8785 / RFC 6962 / ECDSA
verifier, it should **supersede or absorb** this one. Its claim is strictly stronger. Until then
this is the only shipped verifier in the tree, and it says on its face exactly how much less it
checks.

---

## 6. Registers, and a boundary this directory enforces on itself

`src/features/evidence` is **EVIDENCE**: mono for anything emitted verbatim, no motion, no depth,
nothing that a screenshot cannot reproduce. One nuance a reviewer should know about:

`src/design/registers.ts` holds `EVIDENCE_DIRECTORIES`, and it does not list
`src/features/evidence` — that file belongs to the visual-language worker and this worker may not
edit it. Consequence: neither the ESLint fragment nor `register-boundary.test.ts` currently covers
this directory.

Rather than leave the hole open, `tests/unit/evidence/register.test.ts` walks the real module graph
from every file in this directory, using the **same walker** the design package uses, and refuses
any reach into a GPU or DOM-animation package. It also asserts that `EVIDENCE_DIRECTORIES` does
*not* yet name this directory — so the day it does, that assertion goes red and somebody deletes
this paragraph instead of leaving a stale warning in the tree.

---

## 7. Self-registration, and an honest absence

`surface.tsx` exports a `SurfaceDescriptor` and `import.meta.glob('/src/features/*/surface.tsx')`
finds it. `evidence` is **not** in `DECLARED_SURFACES` — that list is the console's list of
promises, it belongs to the console-foundation worker, and this surface was not one of the six the
domain plan promised. `buildRegistry()` therefore admits it as `undeclared`, sorts it after every
promise, and the navigation says:

> This surface registered itself and is not in the console's promise list.

That rendering is left alone. A surface that quietly inserted itself into the promise list would
be the console lying about its own scope on the one screen whose entire subject is not lying about
provenance.

If it is ever promoted, the entry belongs in `src/app/surfaces.ts` with `order: 45` (between
custody and audit), `milestone: 'K5'`, `owner: 'ui/evidence-view'`.

---

## 8. PL-2 — red before green, and demonstrably red

The deliverable is a **refusal**, so a suite that has never been red asserts nothing. Every
negative case in `audit.test.ts` is a real mutation of the sealed bytes, hashed with real
WebCrypto: a flipped hex digit in one declared digest, a truncated file, a deleted file, a
smuggled file, a renamed frame, a self-listing manifest, a duplicated path, a manifest that
violates its contract. The intact case is asserted in the same file, so the refusal is not vacuous.

Two mutants were planted in the implementation during authoring to prove the suite can fail for
the right reason:

| mutant | result |
|---|---|
| `digestAgrees = true` in `auditFiles()` | 6 assertions red, across `audit.test.ts` and `screen.test.tsx` — including the transport-gate test and the honesty-chrome test |
| `canonical: true` in `frameFactsFor()` | the non-canonical-frame-name assertion red |

Both were reverted; this suite is green at 81/81, and no test outside `tests/unit/evidence/`
changed state when the directory was added.

Two further invariants are held by tests rather than by care:

- **The frame-name round trip.** `resources.ts` documents its `~XX` encoding as injective.
  `model.test.ts` decodes **every** frame in the committed bundle and re-encodes it, so the claim
  is checked against 15 real file names rather than three convenient examples. `~47ET~20…`
  decodes to a perfectly good request key and is still refused, because the encoder never escapes
  an unreserved character.
- **The conservation law.** `filesDeclared = matched + mismatched + unreadable + unchecked`, shown
  on the coverage panel. `summarise()` has *no* `else` branch: a row carrying a `DigestState` this
  summary has never heard of is counted in no bucket, so the equation goes unbalanced and the
  screen says so. `model.test.ts` injects exactly that fifth state and requires
  `conserved === false`. A coverage panel whose parts stop summing to its whole is the one defect
  that would otherwise be invisible on a screen made of counters.

---

## 9. Conformance

| file | what it pins |
|---|---|
| `model.test.ts` (22) | the inverse encoding round-trips every committed frame; template matching, including the GET/POST pair on one path and the unowned `clause_ancestry`; the conservation law fails on an unknown state; `LIMITS` is present and says what it must |
| `audit.test.ts` (22) | the intact bundle verifies and its manifest digest equals what `sha256sum` reports; one flipped hex digit fails the audit, names the file, and leaves the other twenty rows matching; truncation reports byte counts; a deleted file is `unreadable`, not a mismatch; a smuggled file is reported only when the source can enumerate itself; **the same verifier makes `BundleTransport` refuse every frame from a tampered bundle** |
| `source.test.ts` (15) | the cross-origin refusal, with its reason; the hash-wins parameter merge; an empty `?bundle=` does not silently fall through to the build default |
| `screen.test.tsx` (16) | no seal before the arithmetic; `unverified` (never `failed`) with no oracle; the full manifest digest in the DOM; the staged note verbatim; the tampered finding rendered with its check name; what reaches the honesty chrome |
| `register.test.ts` (6) | this directory reaches no GPU or motion package, transitively; the descriptor satisfies `validateSurfaceModule` |

A browser spec (`tests/browser/evidence.spec.ts`) is **not** written here: `tests/browser/` belongs
to the cinema-conformance-harness worker and its `_harness/` fixtures do not exist yet. See §10.

---

## 10. Limits of this deliverable

Stated plainly, because a document about honesty that overstates itself is self-refuting.

- **The screen has never been rendered in a real browser**, only in jsdom. There is no Playwright
  spec and no visual baseline; `tests/browser/` is another worker's directory and its harness has
  not landed.
- **Nothing composes a transport yet**, so `manifestIntegrityVerifier()` is exported and tested
  but not wired into a running console. The wiring is one line in whatever becomes the composition
  root.
- **No bundle is served at runtime.** `fixtures/bundles/blk-07` is a source fixture, not a build
  output; until something copies a bundle into `dist/` or sets `VITE_MAINLINE_BUNDLE_URL`, the
  screen renders its honest *no bundle configured* card.
- **`FetchBundleSource` cannot enumerate**, so the `unlisted-file` check is exercised only by the
  listable test source. On a real static host that check is permanently *not established*, and the
  screen says so.
- **The audit is sequential and in-memory**: it reads and hashes every listed file. For the
  committed bundle that is ~120 KB and imperceptible. A bundle two orders of magnitude larger
  would want a streaming digest and a worker thread, and neither is written.
- **The audit runs on the main thread**, not in a Web Worker. `ui.md` D6 puts the full verifier in
  a Worker; for twenty-one files of a few kilobytes each the transfer cost exceeds the hashing
  cost, and a Worker would be ceremony. The full RFC 6962 verifier is a different calculation and
  that is `src/verify/`'s decision to make.
- **Chunk weight.** The surface is a lazy chunk (~10 KB gzip). The seventeen compiled contracts it
  needs to validate a manifest are imported dynamically, so they land in a shared async chunk
  (~26 KB gzip) rather than in this one; `check-budgets` reports the evidentiary shell unchanged
  at 69.8 KB gzip against a 220 KB budget.
