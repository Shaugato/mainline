// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The honesty context (D16).
 *
 * The chrome is the console's own must-not-claim control. Every slot in it is filled by
 * the worker that can actually establish the fact — the transport knows whether it is
 * LIVE or REPLAY, the verifier knows whether the seal held, the data layer knows the
 * bundle digest and the server clock. The shell owns none of those facts and therefore
 * asserts none of them.
 *
 * The default for every slot is `unknown`, and `unknown` renders as the word "unknown"
 * with a visible "unset" marker. A slot nobody filled must look like a slot nobody
 * filled — never like a reassuring green tick that happens to be the initial state.
 */

import { createContext, useCallback, useContext } from 'react';

/** D7 — replay-first. The badge is permanent and non-dismissible. */
export type TransportMode = 'live' | 'replay' | 'unknown';

/** D6 — the in-browser verification result. `unverified` is not `failed`, and says so. */
export type SealState = 'unverified' | 'verifying' | 'verified' | 'failed';

export interface HonestyState {
  /** Whether the bytes on screen came from a live kernel or from a signed bundle. */
  readonly transport: TransportMode;
  /** First 12 hex characters of the EvidenceBundle manifest digest, or null. */
  readonly bundleDigestPrefix: string | null;
  /** Result of the in-browser RFC 8785 / RFC 6962 / ECDSA checks. */
  readonly seal: SealState;
  /** Why the seal is in that state — rendered verbatim, never summarised. */
  readonly sealDetail: string | null;
  /** The corpus commit the displayed ancestry was closed against. */
  readonly corpusRoot: string | null;
  /** server − client, in milliseconds, as measured by the transport. */
  readonly clockSkewMs: number | null;
  /**
   * D17 — which signature-capture path this build compiled, decided at build time from
   * the GT-15 attestation. `unknown` means no attestation existed when the bundle was
   * built, which is a fact about the build and is displayed as one.
   */
  readonly signaturePath: 'webauthn' | 'oidc_envelope' | 'unknown';
  /** The build identifier, so a screenshot names the artefact it came from. */
  readonly buildId: string;
}

export const UNKNOWN_HONESTY: HonestyState = Object.freeze({
  transport: 'unknown',
  bundleDigestPrefix: null,
  seal: 'unverified',
  sealDetail: null,
  corpusRoot: null,
  clockSkewMs: null,
  signaturePath: 'unknown',
  buildId: 'unknown',
});

export type HonestyPatch = Partial<HonestyState>;

export interface HonestyContextValue {
  readonly state: HonestyState;
  readonly publish: (patch: HonestyPatch) => void;
}

export const HonestyContext = createContext<HonestyContextValue | null>(null);

/**
 * Reads the chrome's current claims.
 *
 * Outside a provider this returns the all-unknown state rather than throwing. A missing
 * provider must not be able to take the console down — but it also must not be able to
 * make the chrome say something comforting, which is why the fallback is `unknown` and
 * not a plausible default.
 */
export function useHonesty(): HonestyState {
  return useContext(HonestyContext)?.state ?? UNKNOWN_HONESTY;
}

/**
 * The setter other workers call. Returns a stable function; outside a provider it is a
 * no-op, so a component can publish unconditionally without guarding.
 */
export function useHonestyPublisher(): (patch: HonestyPatch) => void {
  const ctx = useContext(HonestyContext);
  const noop = useCallback(() => undefined, []);
  return ctx?.publish ?? noop;
}
