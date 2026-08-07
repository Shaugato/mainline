// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The register, at runtime.
 *
 * The import boundary (`registers.ts` + `eslint.config.js` + `register-boundary.test.ts`)
 * decides what a DIRECTORY may depend on. This context decides what a COMPONENT INSTANCE
 * may do, and the two answer different questions.
 *
 * `Counter` is one component. Rendered inside the propagation surface it is an
 * INSTRUMENT and it may animate; rendered inside the refusal bar it is EVIDENCE and it
 * may not. A directory rule cannot express that, because it is the same file in both
 * places. So the tree declares the register and the component reads it.
 *
 * The default is `evidence` — the register that forbids the most. A component rendered
 * outside any `RegisterFrame` gets the answer that cannot be wrong rather than the
 * answer that is convenient, which is the same rule `useMotionAllowed()` follows and
 * the same rule `surfaces.ts` applies to an undeclared surface.
 *
 * Split from `RegisterFrame.tsx` on purpose: a module that exports both a component and
 * a hook defeats React Fast Refresh, and the console's ESLint config warns on it.
 */

import { createContext, useContext } from 'react';

import { type Register } from './registers';

export const RegisterContext = createContext<Register>('evidence');

/** The register of the surrounding frame. `evidence` when there is no frame. */
export function useRegister(): Register {
  return useContext(RegisterContext);
}
