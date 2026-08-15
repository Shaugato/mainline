// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The overview surface's self-registration (D8).
 *
 * One file, one `surface` export, no central route table. `src/app/surfaces.ts` globs one
 * directory deep for a file named `surface.tsx` and validates the descriptor; a module that
 * lies about itself is treated exactly like a module that is not there.
 *
 * Every field below has to agree, value for value, with this surface's entry in
 * `DECLARED_SURFACES` — `tests/unit/app/surfaces.test.ts` reads BOTH as text and compares
 * them, because the navigation renders the promise's title and a module that disagreed
 * would not be overruled, it would be unheard.
 *
 * Nothing but the descriptor is exported here, so deleting this one file removes the
 * surface from the console truthfully — the NOT-BUILT-YET card names the milestone that
 * owes it — without touching the screen.
 */

import { type SurfaceDescriptor } from '../../app/surfaces';

import { OverviewScreen } from './OverviewScreen';

export const surface: SurfaceDescriptor = {
  id: 'overview',
  path: '/overview',
  title: 'Overview — what this refuses, and why',
  register: 'evidence',
  order: 5,
  milestone: 'K5',
  Component: OverviewScreen,
};
