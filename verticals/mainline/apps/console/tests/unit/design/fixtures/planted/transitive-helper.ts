// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * PLANTED VIOLATION — the intermediate hop.
 *
 * This is the case an ESLint `no-restricted-imports` rule CANNOT catch when the entry
 * point is what is being reviewed: the entry file is clean, the lint run is green, and the
 * package still lands in the EVIDENCE chunk.
 */

import { animate } from 'motion';

export function ease(): typeof animate {
  return animate;
}
