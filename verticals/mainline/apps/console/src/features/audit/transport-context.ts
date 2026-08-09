// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Where the audit surface gets its bytes.
 *
 * Default `null`, and no fabricated stand-in: `BundleTransport` deliberately has no
 * default verifier — *a bundle player with no verifier is a mock, and this console does
 * not ship one* (`src/data/bundle.ts`) — so a surface that built its own transport would
 * have to choose one. This surface builds nothing and renders an explicit NO SOURCE panel.
 *
 * There is no verifier context here, unlike the custody surface. That is deliberate: the
 * audit screen displays no per-claim recomputation, so it has nothing to verify and no
 * seal to render. What guarantees its bytes is the SAME verification that gated the
 * transport — checked once, before any frame was served.
 */

import { createContext, useContext } from 'react';

import type { MainlineTransport } from '../../data/transport';

export const AuditTransportContext = createContext<MainlineTransport | null>(null);

/** `null` when nobody has provided one. Never a fabricated stand-in. */
export function useAuditTransport(): MainlineTransport | null {
  return useContext(AuditTransportContext);
}
