// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * How this feature is handed a transport.
 *
 * ── WHY THIS EXISTS, AND WHY IT IS LOCAL ─────────────────────────────────────────
 *
 * `src/app` composes no `MainlineTransport` yet. D7 says LIVE and REPLAY differ in ONE
 * LINE OF COMPOSITION, and that line belongs in the shell — but the shell does not have
 * it, and `BundleTransport` cannot be constructed without the `BundleVerifier` that the
 * `verifier-custody-room` worker owes. A feature worker who invented a shell provider
 * would be writing into another worker's file; one who inlined a fixture would be
 * shipping a screen the console made up, which is the exact thing this domain's whole
 * design exists to make impossible.
 *
 * So: a context scoped to this feature, defaulting to `null`, and a surface that renders
 * an HONEST ABSENCE when nothing has been provided. `null` is not an error state — it is
 * the accurate statement that no bytes have been offered, and `useResource` already
 * treats a null transport as `idle` rather than as a failure.
 *
 * ── WHAT REPLACES IT ─────────────────────────────────────────────────────────────
 *
 * When the shell gains a transport provider, this file becomes two lines: re-export the
 * shell's context and delete the local one. Nothing else in this feature changes, because
 * nothing else in this feature knows where the transport came from — `ClauseDiffScreen`
 * takes it as a prop and `ClauseDiff` takes no transport at all.
 */

import { createContext, useContext } from 'react';

import type { MainlineTransport } from '../../data/transport';

export const DiffTransportContext = createContext<MainlineTransport | null>(null);

/** `null` means "nobody has offered any bytes", which is a fact and not a failure. */
export function useDiffTransport(): MainlineTransport | null {
  return useContext(DiffTransportContext);
}
