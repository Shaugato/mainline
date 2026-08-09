// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The gate surface's self-registration (D8).
 *
 * One file, one `surface` export, no central route table. The directory name IS the
 * identity; `src/app/surfaces.ts` globs for it and `validateSurfaceModule` refuses a
 * module that lies about itself — a module that lies is treated exactly like a module
 * that is not there, and the NOT-BUILT-YET card names the milestone that owes it.
 *
 * Nothing but the descriptor is exported here, so deleting this one file removes the
 * surface from the console truthfully (BUILD_PLAN §10.2) without touching the screen.
 */

import { type SurfaceDescriptor } from '../../app/surfaces';

import { GateSurfaceRoot } from './GateSurfaceRoot';

export const surface: SurfaceDescriptor = {
  id: 'gate',
  path: '/gate',
  title: 'Gate — the refusal',
  register: 'evidence',
  order: 10,
  milestone: 'K5',
  Component: GateSurfaceRoot,
};
