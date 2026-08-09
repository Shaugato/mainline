// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Where the silence surface gets its bytes.
 *
 * One client interface (`src/data/transport.ts`), two implementations, and D7 makes the
 * choice between them one line of COMPOSITION. This context is the socket that line plugs
 * into for this surface.
 *
 * The default is `null` and that is not a gap. `BundleTransport` deliberately has no
 * default verifier — a bundle player with no verifier is a mock, and this console does not
 * ship one — so a surface that built its own transport would have to invent a permissive
 * verifier to make itself paint. On a screen whose entire subject is what the system chose
 * not to say, a fabricated source would be the worst possible lie. With no transport
 * provided this surface renders an explicit NO SOURCE panel instead.
 */

import { createContext, useContext } from 'react';

import type { MainlineTransport } from '../../data/transport';

export const SilenceTransportContext = createContext<MainlineTransport | null>(null);

/** `null` when nobody has provided one. Never a fabricated stand-in. */
export function useSilenceTransport(): MainlineTransport | null {
  return useContext(SilenceTransportContext);
}
