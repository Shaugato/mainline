// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `useResource` — the console's entire data-fetching layer (D2).
 *
 * Sixty lines of state machine and an `AbortController` replace a data-fetching
 * library, and the trade is deliberate: six static surfaces, no infinite scroll, no
 * optimistic mutation, no cache invalidation graph. What a library would buy here is
 * a dependency in a tree where the dependency graph is a licence boundary.
 *
 * The state machine has FOUR states and no fifth. In particular there is no state that
 * means "we have stale data and a failure" — a surface either shows a payload that
 * satisfied its contract, or it shows the failure. A safety console that renders the
 * previous permit's counters while the current read is failing is worse than one that
 * renders nothing, because the counters look current.
 *
 * `refusal` is a distinct terminal state rather than an error. A refusal is the
 * product working; painting it in an error colour would be the console editorialising
 * about the database's correct behaviour.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { RefusalLike } from '../app/refusal';
import { refusalFrom } from '../app/refusal';

import type { Exchange, MainlineTransport } from './transport';
import { TransportError } from './transport';
import type { ResourceRequest } from './resources';

export type ResourceState<T> =
  | { readonly status: 'idle' }
  | { readonly status: 'loading' }
  | { readonly status: 'ready'; readonly exchange: Exchange<T>; readonly data: T }
  | {
      readonly status: 'refused';
      readonly refusal: RefusalLike;
    }
  | {
      readonly status: 'failed';
      /** The transport's own failure classification, or `unknown` for anything else. */
      readonly failure: string;
      /** Verbatim. Rendered as-is; never summarised into "something went wrong". */
      readonly detail: string;
    };

export interface UseResourceResult<T> {
  readonly state: ResourceState<T>;
  /** Re-runs the exchange. A human pressing this is the only retry this console has. */
  readonly reload: () => void;
}

export interface UseResourceOptions {
  /** When false the exchange is not performed and the state stays `idle`. */
  readonly enabled?: boolean;
}

/**
 * A stable identity for a request, so an inline object literal in a component body does
 * not re-trigger the effect on every render. It is the same canonicalisation the
 * transport uses to name a frame, minus the resolution step — deliberately cheap,
 * because it runs on every render.
 */
function requestSignature(request: ResourceRequest): string {
  const path = Object.entries(request.path ?? {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${value}`)
    .join('&');
  const query = Object.entries(request.query ?? {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${value}`)
    .join('&');
  const body = request.body === undefined ? '' : JSON.stringify(request.body);
  return `${request.resource}|${path}|${query}|${body}`;
}

export function useResource<T = unknown>(
  transport: MainlineTransport | null,
  request: ResourceRequest,
  options: UseResourceOptions = {},
): UseResourceResult<T> {
  const enabled = options.enabled ?? true;
  const signature = requestSignature(request);

  const [state, setState] = useState<ResourceState<T>>({ status: 'idle' });
  const [nonce, setNonce] = useState(0);

  // The request object is read inside the effect but must not be a dependency of it:
  // its identity changes every render, its signature does not.
  const requestRef = useRef(request);
  requestRef.current = request;

  useEffect(() => {
    if (transport === null || !enabled) {
      setState({ status: 'idle' });
      return undefined;
    }

    const controller = new AbortController();
    let live = true;

    setState({ status: 'loading' });

    transport
      .exchange<T>(requestRef.current, controller.signal)
      .then((exchange) => {
        if (!live) return;
        setState({ status: 'ready', exchange, data: exchange.data });
      })
      .catch((error: unknown) => {
        if (!live) return;
        // An abort is not a failure — it is this effect being superseded, and the
        // replacement is already setting its own state.
        if (controller.signal.aborted) return;

        const refusal = refusalFrom(error);
        if (refusal !== null) {
          setState({ status: 'refused', refusal });
          return;
        }
        if (error instanceof TransportError) {
          setState({ status: 'failed', failure: error.failure, detail: error.detail });
          return;
        }
        setState({
          status: 'failed',
          failure: 'unknown',
          detail: error instanceof Error ? error.message : String(error),
        });
      });

    return () => {
      live = false;
      controller.abort(new Error('useResource: superseded or unmounted'));
    };
    // `signature` stands in for `request`; see requestRef above.
  }, [transport, signature, enabled, nonce]);

  const reload = useCallback(() => {
    setNonce((value) => value + 1);
  }, []);

  return { state, reload };
}

/**
 * Narrowing helper for surfaces that only render on success. It exists so a component
 * cannot accidentally read `.data` off a failed state by writing `state as any`.
 */
export function readyData<T>(state: ResourceState<T>): T | null {
  return state.status === 'ready' ? state.data : null;
}
