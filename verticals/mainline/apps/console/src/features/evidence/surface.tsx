// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Self-registration (D8). One file, one descriptor, no central route table.
 *
 * `evidence` is deliberately NOT in `DECLARED_SURFACES` — that list is the console's
 * list of PROMISES, it belongs to the console-foundation worker, and this surface was
 * not one of the six the domain plan promised. `buildRegistry()` therefore admits it as
 * `undeclared`, sorts it after every promise, and says so in the navigation:
 *
 *   > This surface registered itself and is not in the console's promise list.
 *
 * That is the honest rendering and it is left alone. A surface that quietly inserted
 * itself into the promise list would be the console lying about its own scope on the one
 * screen whose entire subject is not lying about provenance.
 *
 * `order` and `title` below are what this surface would ask for if it were ever
 * promoted; until then the registry's undeclared handling wins, which is correct.
 */

import { type SurfaceDescriptor } from '../../app/surfaces';

import { EvidenceScreen } from './EvidenceScreen';

export const surface: SurfaceDescriptor = {
  id: 'evidence',
  path: '/evidence',
  title: 'Evidence — the bundle',
  register: 'evidence',
  order: 45,
  milestone: 'K5',
  Component: EvidenceScreen,
};
