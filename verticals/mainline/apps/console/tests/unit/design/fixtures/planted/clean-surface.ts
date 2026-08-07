// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE CONTROL.
 *
 * An EVIDENCE-register file that imports a local module and a permitted package. The
 * walker must report NOTHING for it. A checker that flags everything is exactly as useless
 * as one that flags nothing, and without this file the "four violations" assertion would
 * pass for a walker that simply flags every file it sees.
 */

import { useMemo } from 'react';

import { VIRULENCE_CLASSES } from '../../../../../src/design/severity';

export function useBands(): readonly string[] {
  return useMemo(() => [...VIRULENCE_CLASSES], []);
}
