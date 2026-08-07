// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * PLANTED VIOLATION — the exact line the `visual-language` worker's `done_when` names.
 *
 * An EVIDENCE-register file importing `motion/react`. `register-boundary.test.ts` treats
 * this directory as an EVIDENCE register and asserts the walker reports it. Deleting this
 * import makes that test fail, which is the point: the red case is committed.
 */

import { motion } from 'motion/react';

/** Re-exported so `noUnusedLocals` does not delete the violation this file exists to be. */
export const plantedMotion = motion;
