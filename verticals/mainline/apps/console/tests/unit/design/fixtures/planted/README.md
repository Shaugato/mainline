<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# Planted violations — a PL-2 red-capability probe

Every file in this directory is a **deliberate register-boundary violation**. They exist so
that `tests/unit/design/register-boundary.test.ts` can prove it is capable of failing.

PL-2: *for a product whose deliverable is a refusal, a test suite that has never been red
asserts nothing.* The register-boundary test's real assertion is that the console's EVIDENCE
surfaces reach neither `motion` nor `@react-three/*`. That assertion is green on day one and
will stay green — which is exactly the condition under which a broken walker looks identical
to a clean codebase.

So the walker is run twice against the same resolver and the same register law:

| Input | Expected |
|---|---|
| the real `/src/**` source graph | **zero** violations |
| this directory, declared as an EVIDENCE register | **four** violations, named below |

`done_when` for the `visual-language` worker says *a deliberately planted
`import { motion } from 'motion/react'` inside a stub evidence-register file makes the
register-boundary test fail*. These are those files. They are real `.ts` modules with real
imports of real packages — they are type-checked by `tsc` and resolved by the same
`resolveSpecifier` the production walk uses — rather than string fixtures inside the test,
because a string fixture proves the regex works and proves nothing about the resolver.

They live under `tests/` rather than under `src/features/` for one reason: file ownership.
754 paths are allocated across the worker fleet with zero overlap, and `src/features/gate/`
belongs to the `gate-refusal-screen` worker. Planting a file there would corrupt another
worker's directory. The walker does not care — it takes a path→source map and a register
assignment, and `WalkOptions.extraDirectories` supplies the assignment these files need.

## The four plants

| File | Violation |
|---|---|
| `direct-motion.ts` | direct `import { motion } from 'motion/react'` — the exact case named in `done_when` |
| `direct-three.ts` | direct `import * as THREE from 'three'` — GPU package in an EVIDENCE directory |
| `transitive-entry.ts` | clean itself; reaches `motion` through `transitive-helper.ts` — the case ESLint **cannot** catch |
| `transitive-helper.ts` | the intermediate hop; violating in its own right |

`clean-surface.ts` is the control. It imports a local module and a permitted package, and
the walker must report nothing for it — a checker that flags everything is as useless as one
that flags nothing.

**Nothing in this directory is imported by any production module, and nothing here is
executed by any test.** The files are read as text via a Vite `?raw` glob.
