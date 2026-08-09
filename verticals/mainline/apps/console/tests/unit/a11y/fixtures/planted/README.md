<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# Planted accessibility violations

Every file here is **deliberately wrong**, and `../../source-checks.test.ts` requires each
violation to be caught. Beside each one is a `clean-*` counterpart that must produce
nothing, because a checker that flags everything is as useless as one that flags nothing —
and without the clean half that failure mode is invisible, since a rule returning a finding
for every line would still satisfy every "this was caught" assertion.

## Why the `.fixture` suffix

They are real committed bytes, read as text, exactly as `scripts/check-a11y.ts` reads the
shipped sources — and the suffix keeps them out of the TypeScript program and out of the
Vite build. A `.tsx` file containing `dangerouslySetInnerHTML` and a positive `tabIndex`
would otherwise have to typecheck, would have to lint, and would be one careless import
away from being in a chunk. The extension the checks care about (`tsx`, `ts`, `css`) is
supplied explicitly by the test, which also lets the test place a fixture inside the
MEMORY-register directory without creating a file there.

## Why they are not in `src/`

`src/features/*` belongs to other workers, and planting a file in another worker's tree
corrupts it. The same reasoning is recorded in `tests/unit/design/fixtures/planted/`.

## What each file plants

| File | Checks it must trip |
|---|---|
| `violations.tsx.fixture` | `positive-tabindex`, `aria-hidden-interactive`, `click-handler-on-non-interactive`, `img-without-alt`, `inner-html`, `access-key`, `no-canvas-outside-memory`, `signer-sub` |
| `violations.css.fixture` | `focus-visible-outline`, `verbatim-in-pseudo-element` |
| `notes.css.fixture` | `plain-focus-outline-removed` — a NOTE, which must not fail the gate |
| `memory-person.tsx.fixture` | `signer-sub` in its MEMORY-register form (a person identified in the walk) |
| `clean.tsx.fixture` | nothing |
| `clean.css.fixture` | nothing |
