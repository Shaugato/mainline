// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The fleet surface's root component.
 *
 * It lives beside `surface.tsx` rather than inside it so the registration module exports a
 * descriptor and nothing else — React Fast Refresh degrades when one module exports both a
 * component and a value, and the console lints that at `--max-warnings 0`.
 *
 * Three jobs and no more:
 *
 *   1. read the subject from the URL — `#/propagation?lesson=<uuid>`. The console does not
 *      guess which lesson you meant, and a surface with no subject says so;
 *   2. take a transport from `PropagationTransportContext` and render the NO SOURCE panel
 *      when nobody has provided one;
 *   3. fill the honesty chrome slots it is in a position to fill — the transport mode, the
 *      bundle digest prefix and the server-vs-local clock skew (D16). Every one of those
 *      is a fact the transport established; this surface asserts none of them itself.
 */

import { useEffect, useMemo, useSyncExternalStore, type ReactNode } from 'react';

import { useHonestyPublisher } from '../../app/honesty';
import { parseRoute } from '../../app/router';
import { Mono, RegisterFrame } from '../../design/primitives';

import styles from './propagation.module.css';
import { PropagationScreen } from './PropagationScreen';
import { usePropagationTransport } from './transport-context';
import { usePropagationData } from './usePropagationData';

/** The query parameter that addresses a subject: `#/propagation?lesson=<uuid>`. */
export const LESSON_PARAM = 'lesson';

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  window.addEventListener('popstate', onChange);
  return () => {
    window.removeEventListener('hashchange', onChange);
    window.removeEventListener('popstate', onChange);
  };
}

function locationKey(): string {
  return typeof window === 'undefined' ? '' : `${window.location.search}${window.location.hash}`;
}

/**
 * The route's merged query parameters (search plus hash query, hash winning) — the same
 * parsing the shell's router performs, reused rather than reimplemented so `?cinema=1` and
 * `?lesson=…` behave identically in either position.
 */
function useRouteParams(): URLSearchParams {
  const key = useSyncExternalStore(subscribe, locationKey, () => '');
  return useMemo(() => {
    const hashAt = key.indexOf('#');
    const search = hashAt >= 0 ? key.slice(0, hashAt) : key;
    const hash = hashAt >= 0 ? key.slice(hashAt) : '';
    return parseRoute(hash, search, []).params;
  }, [key]);
}

function NoSubject(): ReactNode {
  return (
    <RegisterFrame register="evidence">
      <div className={styles.surface} data-testid="propagation-no-subject">
        <h1 className={styles.title}>Propagation — where the lesson travelled</h1>
        <section className={styles.panel}>
          <p className={styles.prose}>
            This surface renders the fleet response to ONE lesson and does not choose one for
            you. Address a lesson by its identifier —{' '}
            <Mono>#/propagation?{LESSON_PARAM}=&lt;uuid&gt;</Mono> — and the console will read
            that lesson, every site&apos;s answer to it, and every conflict still open against
            it.
          </p>
        </section>
      </div>
    </RegisterFrame>
  );
}

export function PropagationSurfaceRoot(): ReactNode {
  const params = useRouteParams();
  const lessonId = params.get(LESSON_PARAM);
  const transport = usePropagationTransport();
  const publish = useHonestyPublisher();

  // Hooks run unconditionally; the empty subject is handled by the render below, and
  // `usePropagationData` performs no exchange when the transport is null.
  const state = usePropagationData(transport, lessonId ?? '');

  const description = transport?.describe() ?? null;
  const mode = description?.mode ?? null;
  const digestPrefix = description?.bundleDigestPrefix ?? null;
  const clockSkewMs = state.status === 'ready' ? state.exchange.clockSkewMs : null;

  useEffect(() => {
    publish({
      transport: mode ?? 'unknown',
      bundleDigestPrefix: digestPrefix,
      clockSkewMs,
    });
  }, [publish, mode, digestPrefix, clockSkewMs]);

  if (lessonId === null || lessonId === '') return <NoSubject />;

  return <PropagationScreen lessonId={lessonId} state={state} noSource={transport === null} />;
}
