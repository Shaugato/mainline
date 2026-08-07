// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * PLANTED VIOLATION — reached transitively.
 *
 * Nothing in this file is forbidden. It imports one local module, and that module imports
 * `motion`. A per-file lint reports nothing here; the module-graph walk reports the chain.
 */

import { ease } from './transitive-helper';

export const plantedTransitive = ease;
