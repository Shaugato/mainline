// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The fleet surface's self-registration (D8).
 *
 * One file, one `surface` export, no central route table. The directory name IS the
 * identity; `src/app/surfaces.ts` globs for it and `validateSurfaceModule` refuses a
 * module that lies about itself. Deleting this one file removes the surface from the
 * console truthfully (BUILD_PLAN §10.2) without touching the screen.
 *
 * ── WHY `register` SAYS `evidence` WHEN THE DIRECTORY LAW SAYS `instrument` ──────
 *
 * `src/design/registers.ts` — owned by the visual-language worker — lists
 * `src/features/propagation` under `INSTRUMENT_DIRECTORIES`, and `src/app/surfaces.ts`'s
 * promise list records the same. INSTRUMENT permits DOM animation; EVIDENCE forbids it.
 *
 * This descriptor elects the STRICTER of the two, deliberately and visibly:
 *
 *   • the brief for this surface states both directories are EVIDENCE — no motion, no 3D,
 *     no chart of people;
 *   • nothing on this screen is a transition that is itself the fact, which is the only
 *     thing INSTRUMENT's licence to move is for; and
 *   • electing EVIDENCE is legal under both laws — EVIDENCE's forbidden set is a superset
 *     of INSTRUMENT's, so this directory violates neither.
 *
 * The consequence is a visible disagreement: the shell writes `data-register="instrument"`
 * on the wrapper it owns, from its promise list, while this surface's own `RegisterFrame`
 * declares `evidence` on the subtree that actually renders. That disagreement is left in
 * the open rather than resolved by editing another worker's file, and it is recorded as a
 * cross-domain note. `tests/unit/propagation/register.test.ts` asserts the part that
 * matters either way: this directory imports no animation and no GPU package, directly or
 * transitively.
 */

import { type SurfaceDescriptor } from '../../app/surfaces';

import { PropagationSurfaceRoot } from './PropagationSurfaceRoot';

export const surface: SurfaceDescriptor = {
  id: 'propagation',
  path: '/propagation',
  title: 'Propagation — where the lesson travelled',
  register: 'evidence',
  order: 60,
  milestone: 'K4',
  Component: PropagationSurfaceRoot,
};
