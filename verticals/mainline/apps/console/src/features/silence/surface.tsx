// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The silence surface's self-registration (D8).
 *
 * One file, one `surface` export, no central route table. The directory name IS the
 * identity; `src/app/surfaces.ts` globs for it and `validateSurfaceModule` refuses a module
 * that lies about itself. Deleting this one file removes the surface truthfully
 * (BUILD_PLAN §10.2) without touching the screen — and the NOT-BUILT-YET card would then
 * name the milestone that owes it, which on this surface is the honest outcome: a console
 * that quietly dropped its silence ledger would be reporting less than it knows.
 *
 * `src/features/silence` is an EVIDENCE directory in `src/design/registers.ts`, in
 * `eslint.config.js` and in the console's promise list, so this descriptor agrees with all
 * three: no motion, no GPU, nothing that moves that a screenshot could not reproduce.
 */

import { type SurfaceDescriptor } from '../../app/surfaces';

import { SilenceSurfaceRoot } from './SilenceSurfaceRoot';

export const surface: SurfaceDescriptor = {
  id: 'silence',
  path: '/silence',
  title: 'Silence — what was not surfaced',
  register: 'evidence',
  order: 70,
  milestone: 'K4',
  Component: SilenceSurfaceRoot,
};
