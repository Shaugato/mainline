// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The audit surface's self-registration (D8).
 *
 * One file, one `surface` export, no central route table. Deleting this file removes the
 * surface truthfully: the NOT-BUILT-YET card names K6 as the milestone that owes it.
 */

import { type SurfaceDescriptor } from '../../app/surfaces';

import { AuditRoot } from './AuditRoot';

export const surface: SurfaceDescriptor = {
  id: 'audit',
  path: '/audit',
  title: 'Audit — the MCP surface',
  register: 'evidence',
  order: 50,
  milestone: 'K6',
  Component: AuditRoot,
};
