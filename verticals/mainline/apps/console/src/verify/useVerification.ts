// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `useVerification()` — the verifier as React state.
 *
 * FIVE states and no sixth, for the same reason `useResource` has four and
 * `useBundleAudit` has five: there is no state that means *we have a partial result and a
 * failure*. A verification surface that renders half a check list beside an error is worse
 * than one that renders the error, because the half-list looks like a finding.
 *
 *   `idle`      nothing to verify, and the reason travels with the state.
 *   `verifying` running. The surface shows an amber seal, never a green one.
 *   `settled`   the run finished. Its own `overall` may still be `fail` or `bounded`.
 *   `failed`    the VERIFIER itself threw — a worker that died, a payload that would not
 *               decode. Distinct from a bundle that failed verification, because those two
 *               sentences mean opposite things about who is at fault.
 *
 * Abort is supersession, not failure: an unmount or a changed payload disposes the
 * verifier and drops the in-flight promise, exactly as the other two hooks do it.
 *
 * `verifier` is injectable. The default constructs a worker-backed one and disposes it on
 * unmount; a caller that already owns a verifier (the cinema harness, a test) passes it in
 * and keeps ownership.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { Verifier, VerifierInfo } from './client';
import { createVerifier } from './client';
import type { VerifierConfig } from './config';
import { resolveVerifierConfig } from './config';
import type { CheckReport, LedgerPayload } from './ledger';

export type VerificationState =
  | { readonly status: 'idle'; readonly reason: string }
  | { readonly status: 'verifying' }
  | { readonly status: 'settled'; readonly report: CheckReport; readonly info: VerifierInfo }
  | { readonly status: 'failed'; readonly detail: string };

export interface UseVerificationInput {
  /** `null` when there is nothing to check; `reason` is then what the screen shows. */
  readonly payload: LedgerPayload | null;
  /** Why `payload` is null. Rendered verbatim; never paraphrased. */
  readonly reason?: string;
  readonly config?: VerifierConfig;
  /** Supply to keep the report deterministic under cinema mode (D12). */
  readonly at?: string;
  /** Bring your own verifier; the caller then owns its lifetime. */
  readonly verifier?: Verifier;
}

export function useVerification(input: UseVerificationInput): VerificationState {
  const { payload, verifier: supplied, at } = input;
  const reason = input.reason ?? 'No ledger payload has been loaded, so nothing has been checked.';
  const suppliedConfig = input.config;

  const [state, setState] = useState<VerificationState>(() =>
    payload === null ? { status: 'idle', reason } : { status: 'verifying' },
  );

  /*
   * CONTENT keys, not identities — the same idiom `useResource` uses, and for a sharper
   * reason here.
   *
   * A parent that builds its payload or its config inline hands this hook a new object on
   * every render. Keying the effect on identity would restart verification, whose
   * `setState` renders again, which builds another object: a loop that presents as a
   * verification that never settles. On a surface whose entire subject is whether the
   * arithmetic ran, "still checking, for ever" is the worst available failure, so the hook
   * defends against it rather than documenting the requirement and hoping.
   */
  const signature = useMemo(() => (payload === null ? '' : JSON.stringify(payload)), [payload]);
  const configKey = useMemo(
    () => (suppliedConfig === undefined ? '' : JSON.stringify(suppliedConfig)),
    [suppliedConfig],
  );

  const payloadRef = useRef(payload);
  payloadRef.current = payload;
  const configRef = useRef(suppliedConfig);
  configRef.current = suppliedConfig;

  useEffect(() => {
    const current = payloadRef.current;
    if (current === null) {
      setState({ status: 'idle', reason });
      return undefined;
    }

    const config = configRef.current ?? resolveVerifierConfig();
    let live = true;
    const owned = supplied === undefined;
    const verifier = supplied ?? createVerifier();
    setState({ status: 'verifying' });

    void (async (): Promise<void> => {
      try {
        const info = await verifier.describe();
        const report = await verifier.verifyLedgerPayload(current, config, at);
        if (live) setState({ status: 'settled', report, info });
      } catch (error) {
        if (live) {
          setState({
            status: 'failed',
            detail: error instanceof Error ? error.message : String(error),
          });
        }
      }
    })();

    return () => {
      live = false;
      if (owned) verifier.dispose();
    };
    // `signature` and `configKey` stand in for `payload` and `config`; see the refs above.
    // `supplied` is deliberately an IDENTITY dependency: a verifier owns a worker, and a
    // caller that swaps it has swapped the thing doing the arithmetic.
  }, [signature, configKey, at, supplied, reason]);

  return state;
}
