// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The clause-diff surface's self-registration (D8).
 *
 * One file, one `surface` export, no central route table. `src/app/surfaces.ts` globs for
 * `src/features/<id>/surface.tsx` and `validateSurfaceModule` refuses a module that lies
 * about itself; deleting this one file removes the surface from the console truthfully
 * (BUILD_PLAN §10.2) without touching the panel, which the gate screen also embeds.
 *
 * `diff` is deliberately NOT in `DECLARED_SURFACES` — that promise list belongs to the
 * console-foundation worker and `docs/leads/ui.md` §5 gives the clause diff to the gate
 * screen rather than to a route of its own. The registry admits an undeclared surface on
 * purpose: it classifies it into the most restrictive register (EVIDENCE, which is
 * correct) and sorts it after every promise. So the diff is addressable at `#/diff` for
 * the browser spec and for an engineer following a blame pointer, and no other worker's
 * file had to change to make that true.
 */

import { type SurfaceDescriptor } from '../../app/surfaces';

import { ClauseDiffScreen } from './ClauseDiffScreen';

export const surface: SurfaceDescriptor = {
  id: 'diff',
  path: '/diff',
  title: 'Diff — what “weakened” meant',
  register: 'evidence',
  // Immediately after the gate (10) and before the ancestry walk (20): the diff is what
  // a reader opens next after a refusal names a clause. Undeclared surfaces are sorted
  // after every promise by `buildRegistry` regardless, so this is a statement of intent
  // for the day the promise list gains an entry, not a claim about today's navigation.
  order: 15,
  milestone: 'K5',
  Component: ClauseDiffScreen,
};
