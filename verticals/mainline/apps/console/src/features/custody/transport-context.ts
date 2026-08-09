// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Where the custody surface gets its bytes, and its verifier.
 *
 * Two contexts, both defaulting to `null`, and neither manufacturing a stand-in.
 *
 * **Transport.** `BundleTransport` deliberately has no default verifier — *a bundle player
 * with no verifier is a mock, and this console does not ship one* (`src/data/bundle.ts`).
 * A surface that built its own transport would have to choose one, so this surface builds
 * nothing and renders an explicit NO SOURCE panel instead.
 *
 * **Verifier.** `null` here means "construct one per screen", which is the normal case:
 * `useVerification` spawns a worker and disposes it on unmount. A caller supplies one when
 * it already owns the lifetime — the cinema harness, which needs the verification to be
 * deterministic and the worker to outlive a re-render, and the unit tests, which have no
 * `Worker` constructor at all.
 */

import { createContext, useContext } from 'react';

import type { MainlineTransport } from '../../data/transport';
import type { Verifier } from '../../verify/client';
import type { VerifierConfig } from '../../verify/config';

export const CustodyTransportContext = createContext<MainlineTransport | null>(null);

/** `null` when nobody has provided one. Never a fabricated stand-in. */
export function useCustodyTransport(): MainlineTransport | null {
  return useContext(CustodyTransportContext);
}

export const CustodyVerifierContext = createContext<Verifier | null>(null);

/** `null` means "this screen owns its own worker", not "verification is off". */
export function useCustodyVerifier(): Verifier | null {
  return useContext(CustodyVerifierContext);
}

/**
 * The trust anchor, overridable for tests and the harness.
 *
 * `null` means "resolve from the build and the URL", which is what production does.
 * Providing one is how a spec pins the published example key without setting an
 * environment variable for the whole build.
 */
export const CustodyConfigContext = createContext<VerifierConfig | null>(null);

export function useCustodyConfig(): VerifierConfig | null {
  return useContext(CustodyConfigContext);
}
