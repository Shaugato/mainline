// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The custody surface's self-registration (D8).
 *
 * One file, one `surface` export, no central route table. `src/app/surfaces.ts` globs one
 * directory deep for a file named `surface.tsx` and validates the descriptor; a module that
 * lies about itself is treated exactly like a module that is not there.
 *
 * Nothing but the descriptor is exported here, so deleting this one file removes the
 * surface from the console truthfully — the NOT-BUILT-YET card names the milestone that
 * owes it — without touching the screen.
 */

import { type SurfaceDescriptor } from '../../app/surfaces';

import { CustodyRoot } from './CustodyRoot';

export const surface: SurfaceDescriptor = {
  id: 'custody',
  path: '/custody',
  title: 'Custody — the chain',
  register: 'evidence',
  order: 40,
  milestone: 'K2',
  Component: CustodyRoot,
};
