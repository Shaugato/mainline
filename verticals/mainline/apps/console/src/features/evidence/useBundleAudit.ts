// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The audit as a React state machine.
 *
 * FIVE states and no sixth, for the same reason `useResource` has four: there is no
 * state that means "we have a partial result and a failure". A verification surface
 * that renders half an inventory beside an error is worse than one that renders the
 * error, because the half-inventory looks like a finding.
 *
 *   `idle`        nothing to audit, and the reason why is carried verbatim.
 *   `unavailable` there is a bundle but no digest oracle — an insecure origin. This is
 *                 NOT a failure: the bundle has not been accused of anything.
 *   `auditing`    running, with a file count so a slow read is visibly progress.
 *   `settled`     the audit finished. Its own verdict may still be `failed`.
 *   `error`       the audit itself threw. Distinct from a bundle that failed the audit.
 *
 * Abort is supersession, not failure: an unmount or a changed source aborts the signal
 * and the rejected promise is dropped, exactly as `useResource` does it.
 */

import { useEffect, useState } from 'react';

import type { BundleSource } from '../../data/bundle';
import type { SchemaRegistry } from '../../data/schema';

import { AuditAborted, auditBundle, type BundleAudit } from './audit';
import type { DigestOracle } from './digest';

export type AuditState =
  | { readonly status: 'idle'; readonly reason: string }
  | { readonly status: 'unavailable'; readonly reason: string }
  | { readonly status: 'auditing'; readonly done: number; readonly total: number | null }
  | { readonly status: 'settled'; readonly audit: BundleAudit }
  | { readonly status: 'error'; readonly detail: string };

export interface UseBundleAuditInput {
  /** `null` when no bundle is configured; `reason` is then what the screen shows. */
  readonly source: BundleSource | null;
  /** `null` when this origin exposes no WebCrypto. */
  readonly oracle: DigestOracle | null;
  /** Why `source` or `oracle` is null. Rendered verbatim; never paraphrased. */
  readonly reason: string;
  readonly registry?: SchemaRegistry;
  readonly clock?: () => string;
}

export function useBundleAudit(input: UseBundleAuditInput): AuditState {
  const { source, oracle, reason, registry, clock } = input;

  const [state, setState] = useState<AuditState>(() =>
    source === null
      ? { status: 'idle', reason }
      : oracle === null
        ? { status: 'unavailable', reason }
        : { status: 'auditing', done: 0, total: null },
  );

  useEffect(() => {
    if (source === null) {
      setState({ status: 'idle', reason });
      return undefined;
    }
    if (oracle === null) {
      setState({ status: 'unavailable', reason });
      return undefined;
    }

    const controller = new AbortController();
    let live = true;
    setState({ status: 'auditing', done: 0, total: null });

    auditBundle({
      source,
      oracle,
      signal: controller.signal,
      onProgress: (done, total) => {
        if (live) setState({ status: 'auditing', done, total });
      },
      ...(registry === undefined ? {} : { registry }),
      ...(clock === undefined ? {} : { clock }),
    }).then(
      (audit) => {
        if (live) setState({ status: 'settled', audit });
      },
      (error: unknown) => {
        if (!live) return;
        // Supersession, not failure. The replacement effect is already setting state.
        if (error instanceof AuditAborted || controller.signal.aborted) return;
        setState({
          status: 'error',
          detail: error instanceof Error ? error.message : String(error),
        });
      },
    );

    return () => {
      live = false;
      controller.abort(new Error('useBundleAudit: superseded or unmounted'));
    };
  }, [source, oracle, reason, registry, clock]);

  return state;
}
