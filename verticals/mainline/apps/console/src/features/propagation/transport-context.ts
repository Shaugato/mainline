// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Where the fleet surface gets its bytes.
 *
 * The console has ONE client interface (`src/data/transport.ts`) with two implementations
 * — `HttpTransport` and the verified `BundleTransport` — and D7 makes the choice between
 * them one line of COMPOSITION. This context is the socket that line plugs into for this
 * surface.
 *
 * The default is `null`, and that is not a gap. A surface that could build its own
 * transport would have to choose a verifier, and `BundleTransport` deliberately has no
 * default one: a bundle player with no verifier is a mock, and this console does not ship
 * one. Manufacturing a permissive verifier here to make a screen paint would be exactly
 * the lie the transport was shaped to prevent, so with no transport provided this surface
 * renders an explicit NO SOURCE panel naming what is missing.
 *
 * The composition root is the shell (`src/app`), which does not yet provide one; that is a
 * cross-domain note rather than something to paper over here. Tests and the cinema harness
 * provide a transport through this context directly.
 */

import { createContext, useContext } from 'react';

import type { MainlineTransport } from '../../data/transport';

export const PropagationTransportContext = createContext<MainlineTransport | null>(null);

/** `null` when nobody has provided one. Never a fabricated stand-in. */
export function usePropagationTransport(): MainlineTransport | null {
  return useContext(PropagationTransportContext);
}
